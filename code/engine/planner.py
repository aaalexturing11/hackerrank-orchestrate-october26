"""Turn eligible observations into contract steps.

Activity rows can name a resource when the detail says "Target resource:".
They do not set presence. A partial account snapshot is not global absence.
An absence observed before the request does not prove absence at audit time.
Identifier-free rows in a multi-user file are not assigned by timestamp proximity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from code.config import KNOWN_SYSTEMS
from code.engine.classifier import RequestIntent, classify_request
from code.engine.step_builder import finding, remediation, sort_steps, verification
from code.engine.systems import canonical_system
from code.identity.resolver import IdentityResolver
from code.ingestion.normalize import bag_from_mapping, make_observation
from code.models import ActivityRecord, AuditStep, DeletionRequest, Observation, ResourceState
from code.policy.decide import Treatment, category_for, decide
from code.timeline.reconstructor import TimelineReconstructor

ANCHOR_WINDOW = timedelta(minutes=10)
ANCHOR_EVENTS = frozenset(
    {
        "DELETE_RECORD",
        "ANONYMIZE_RECORD",
        "REDACT_RECORD",
        "DISABLE_DATA_FLOW",
        "BLOCK_RESTORE",
    }
)
PROFILE_TYPES = frozenset({"USER_PROFILE", "customer_profiles"})
_CANONICAL = KNOWN_SYSTEMS
_CATEGORY_SYSTEM = {
    "USER_PROFILE": "account_service",
    "SEARCH_INDEX_ENTRY": "search_service",
    "ANALYTICS_PROFILE": "analytics_platform",
    "PRODUCT_TELEMETRY": "analytics_platform",
    "MARKETING_PROFILE": "marketing_platform",
    "SUPPORT_MESSAGE": "support_platform",
    "SUPPORT_ATTACHMENT": "support_platform",
    "USER_EXPORT": "export_service",
    "DATA_FLOW": "integration_service",
    "BACKUP_ARCHIVE": "backup_service",
    "SECURITY_AUDIT_LOG": "security_service",
    "ACCOUNT_TOMBSTONE": "identity_service",
    "LEGAL_HOLD_RECORD": "legal_service",
    "EMAIL_DELIVERY_LOG": "email_delivery_service",
    "CACHE_ENTRY": "cache_service",
}


@dataclass(frozen=True)
class AuditDecision:
    case_id: str
    deletion_status: str
    steps: list[AuditStep]
    notes: tuple[str, ...] = ()


class DeletionPlanner:
    def __init__(
        self,
        resolver: IdentityResolver,
        observations: list[Observation],
        activities: list[ActivityRecord],
    ) -> None:
        self.resolver = resolver
        self.observations = observations
        self.activities = activities
        self.timeline = TimelineReconstructor()

    def audit(self, request: DeletionRequest) -> AuditDecision:
        classification = classify_request(request.request_text)
        if classification.intent is not RequestIntent.DELETION:
            return AuditDecision(request.case_id, "NOT_APPLICABLE", [], ("request does not authorize deletion",))
        resolved = self.resolver.resolve_email(request.email, audit_at=request.audit_at)
        if resolved.status != "unique" or resolved.user_id is None:
            return AuditDecision(
                request.case_id,
                "INCOMPLETE",
                [],
                (f"identity is {resolved.status}",),
            )
        aliases = self.resolver.aliases_at(resolved.user_id, request.audit_at)
        anchored = _anchored_resources(request, self.activities, self.observations, aliases)
        linked = {
            resource_id
            for _system, resource_id in self.resolver.resources_for_user(
                resolved.user_id, request.audit_at, self.observations
            )
        }
        linked.update(anchored)
        linked.update(_historical_lineage(aliases, self.observations, request.audit_at))
        selected = [
            row
            for row in self.observations
            if row.eligible_at(request.audit_at)
            and not row.is_claim
            and row.resource_id
            and not _stale_absence(row, request.requested_at)
            and (aliases.intersects(row.identifiers) or row.resource_id in linked)
        ]
        selected.extend(_account_omissions(anchored, request, self.observations))
        states = _collapse(self.timeline.reconstruct(selected, request.audit_at))
        gap_rows = _historical_state_gaps(linked, request, self.observations, selected)
        gap_states = [
            state
            for state in _collapse(self.timeline.reconstruct(gap_rows, request.audit_at, require_package=False))
            if state.resource_id not in {item.resource_id for item in states}
        ]
        treatments: list[tuple[ResourceState, Treatment]] = []
        for state in states:
            treatment = decide(state, request.audit_at)
            if treatment is not None:
                treatments.append((state, treatment))
        violations = [pair for pair in treatments if not pair[1].compliant]
        status = "INCOMPLETE" if violations or not treatments else "COMPLETE"
        if any(state.presence == "conflict" for state, _treatment in treatments):
            status = "INCOMPLETE"
        if status == "INCOMPLETE":
            for state in gap_states:
                treatment = decide(state, request.audit_at)
                if treatment is not None and treatment.compliant:
                    treatments.append((state, treatment))
        steps = _steps(treatments, evidence_for_compliant=status == "COMPLETE", audit_at=request.audit_at)
        return AuditDecision(request.case_id, status, steps)


def _historical_lineage(aliases, observations: list[Observation], audit_at: datetime) -> set[str]:
    """Resource ids owned by this subject in a snapshot or event at or before audit_at.

    The file that carries the identity may have been packaged later. Those rows
    are not state. A resource claimed by another subject's identifiers is left
    unresolved.
    """
    grouped: dict[str, list[Observation]] = {}
    for row in observations:
        if row.is_claim or not row.resource_id or row.identifiers.is_empty():
            continue
        moment = row.observed_at or row.captured_at
        if moment is None or moment > audit_at:
            continue
        grouped.setdefault(row.resource_id, []).append(row)
    owned: set[str] = set()
    for resource_id, rows in grouped.items():
        matched = [row for row in rows if aliases.intersects(row.identifiers)]
        competing = [row for row in rows if not aliases.intersects(row.identifiers)]
        if matched and not competing:
            owned.add(resource_id)
    return owned


def _historical_state_gaps(
    linked: set[str],
    request: DeletionRequest,
    observations: list[Observation],
    selected: list[Observation],
) -> list[Observation]:
    """State rows whose event is before the audit but whose package is later.

    They fill a resource that has no eligible observation. They never replace one.
    """
    covered = {row.resource_id for row in selected if row.resource_id}
    gaps: list[Observation] = []
    for row in observations:
        if row.is_claim or not row.resource_id or row.resource_id not in linked:
            continue
        if row.resource_id in covered:
            continue
        if row.observed_at is None or row.observed_at > request.audit_at:
            continue
        if row.captured_at is not None and row.captured_at <= request.audit_at:
            continue
        if _stale_absence(row, request.requested_at):
            continue
        gaps.append(row)
    return gaps


def _stale_absence(row: Observation, requested_at: datetime) -> bool:
    """An absence seen before the request does not prove absence at audit time."""
    if row.presence != "absent":
        return False
    moment = row.observed_at or row.captured_at
    return moment is not None and moment < requested_at


@dataclass(frozen=True)
class ResourceScope:
    """A resource placed in deletion scope by evidence, not by time proximity."""

    system_id: str
    resource_id: str
    subject_id: str | None
    subject_source: str
    workflow_source: str
    competing: bool


def resource_scopes(request, activities, observations, aliases) -> list[ResourceScope]:
    """Workflow scope is the literal target named by a deletion worker.

    Activity details have no case, user, trace, or correlation id. A worker row
    that does not name its target stays out of scope, including inside the
    ten-minute window around reported_at.
    """
    start = request.reported_at - ANCHOR_WINDOW
    end = request.reported_at + ANCHOR_WINDOW
    scopes: list[ResourceScope] = []
    for activity in activities:
        if activity.source_system != "deletion_worker" or activity.event_type not in ANCHOR_EVENTS:
            continue
        if "Target resource:" not in activity.details:
            continue
        if activity.event_time < start or activity.event_time > end or activity.event_time > request.audit_at:
            continue
        competing = _belongs_to_other(activity.resource_id, observations, aliases, request.audit_at)
        scopes.append(
            ResourceScope(
                system_id=activity.target_system or "",
                resource_id=activity.resource_id,
                subject_id=None,
                subject_source="named_target_only",
                workflow_source=activity.activity_id,
                competing=competing,
            )
        )
    return scopes


def _anchored_resources(request, activities, observations, aliases) -> set[str]:
    return {
        scope.resource_id
        for scope in resource_scopes(request, activities, observations, aliases)
        if not scope.competing
    }


def _belongs_to_other(resource_id: str, observations, aliases, audit_at) -> bool:
    for row in observations:
        if row.resource_id != resource_id or row.is_claim or not row.eligible_at(audit_at):
            continue
        if row.identifiers.is_empty():
            continue
        if not aliases.intersects(row.identifiers):
            return True
    return False


def _account_omissions(anchored: set[str], request: DeletionRequest, observations: list[Observation]) -> list[Observation]:
    created: list[Observation] = []
    known = {
        row.resource_id
        for row in observations
        if row.resource_id in anchored and row.eligible_at(request.audit_at) and not row.is_claim
    }
    snapshots: dict[str, Observation] = {}
    for row in observations:
        if row.record_type not in PROFILE_TYPES or row.presence != "present" or row.is_claim:
            continue
        if not row.eligible_at(request.audit_at) or row.captured_at is None:
            continue
        if row.captured_at < request.reported_at:
            continue
        current = snapshots.get(row.evidence_id)
        if current is None or (current.captured_at and row.captured_at > current.captured_at):
            snapshots[row.evidence_id] = row
    if not snapshots:
        return created
    latest = max(snapshots.values(), key=lambda row: row.captured_at or request.audit_at)
    present_ids = {
        row.resource_id
        for row in observations
        if row.evidence_id == latest.evidence_id and row.presence == "present" and row.record_type in PROFILE_TYPES
    }
    for resource_id in sorted(anchored):
        if not resource_id.startswith("account_") or resource_id in known or resource_id in present_ids:
            continue
        created.append(
            make_observation(
                evidence_id=latest.evidence_id,
                system_id="account_service",
                resource_id=resource_id,
                observed_at=latest.captured_at,
                captured_at=latest.captured_at,
                record_type="USER_PROFILE",
                replica_role="unspecified",
                replica_name=None,
                presence="absent",
                identifiers=bag_from_mapping({}),
                identifiers_exposed=None,
                source_locator=f"{latest.evidence_id}:account-snapshot-omission:{resource_id}",
                limitations="named account is not in the latest eligible account snapshot; this is not global absence",
                confidence="low",
                result_token="SNAPSHOT_OMISSION",
            )
        )
    return created


def _collapse(states: list[ResourceState]) -> list[ResourceState]:
    grouped: dict[tuple[str, str], list[ResourceState]] = {}
    for state in states:
        system_id = canonical_system(state.system_id, state.resource_id)
        if system_id not in _CANONICAL:
            system_id = _CATEGORY_SYSTEM.get(category_for(state.record_type) or "", system_id)
        grouped.setdefault((system_id, state.resource_id), []).append(state)
    chosen: list[ResourceState] = []
    for (system_id, resource_id), rows in grouped.items():
        present = [row for row in rows if row.presence == "present"]
        if present:
            winner = max(present, key=lambda row: (row.observed_at or row.captured_at, row.evidence_id or ""))
        else:
            absent = [row for row in rows if row.presence == "absent"]
            if not absent:
                continue
            winner = max(absent, key=lambda row: (row.observed_at or row.captured_at, row.evidence_id or ""))
        chosen.append(
            ResourceState(
                system_id=system_id,
                resource_id=resource_id,
                replica_role=winner.replica_role,
                replica_name=winner.replica_name,
                presence=winner.presence,
                evidence_id=winner.evidence_id,
                observed_at=winner.observed_at,
                captured_at=winner.captured_at,
                record_type=winner.record_type,
                identifiers_exposed=winner.identifiers_exposed,
                anonymized=winner.anonymized,
                redacted=winner.redacted,
                flow_enabled=winner.flow_enabled,
                restore_blocked=winner.restore_blocked,
                retention_until=winner.retention_until,
                unresolved_conflict=winner.unresolved_conflict,
                limitations=winner.limitations,
                confidence=winner.confidence,
                linkable=winner.linkable,
            )
        )
    return chosen


def _steps(
    treatments: list[tuple[ResourceState, Treatment]],
    *,
    evidence_for_compliant: bool,
    audit_at: datetime,
) -> list[AuditStep]:
    steps: list[AuditStep] = []
    for state, treatment in treatments:
        if state.evidence_id is None:
            continue
        packaged_later = state.captured_at is not None and state.captured_at > audit_at
        if treatment.finding_operation and treatment.remediation_operation:
            if packaged_later:
                continue
            steps.append(
                finding(
                    system_id=state.system_id,
                    resource_id=state.resource_id,
                    operation=treatment.finding_operation,
                    evidence_id=state.evidence_id,
                )
            )
            steps.append(
                remediation(
                    system_id=state.system_id,
                    resource_id=state.resource_id,
                    operation=treatment.remediation_operation,
                )
            )
            steps.append(
                verification(
                    system_id=state.system_id,
                    resource_id=state.resource_id,
                    operation=treatment.verification_operation,
                    evidence_id="",
                )
            )
            continue
        if packaged_later and evidence_for_compliant:
            continue
        evidence_id = state.evidence_id if evidence_for_compliant else ""
        steps.append(
            verification(
                system_id=state.system_id,
                resource_id=state.resource_id,
                operation=treatment.verification_operation,
                evidence_id=evidence_id,
            )
        )
    return sort_steps(steps)
