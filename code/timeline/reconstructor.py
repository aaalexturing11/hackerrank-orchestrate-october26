"""Reconstruct per-replica resource state at an audit timestamp.

Claims do not become state. Unknown presence does not overwrite a real
observation. Resources with no eligible observation are omitted rather than
marked absent.
"""

from __future__ import annotations

from datetime import datetime

from code.ingestion.normalize import bag_from_mapping, make_observation
from code.models import ActivityRecord, Observation, RecreationRisk, ReplicationDrift, ResourceState


def activities_as_claims(activities: list[ActivityRecord]) -> list[Observation]:
    """Keep workflow results as claims. SUCCESS is not presence or absence."""
    claims: list[Observation] = []
    for activity in activities:
        claims.append(
            make_observation(
                evidence_id=activity.activity_id,
                system_id=activity.target_system or activity.source_system or "unspecified",
                resource_id=activity.resource_id,
                observed_at=activity.event_time,
                captured_at=activity.event_time,
                record_type=None,
                replica_role="unspecified",
                replica_name=None,
                presence="unknown",
                identifiers=bag_from_mapping({}),
                identifiers_exposed=None,
                source_locator=activity.activity_id,
                limitations=f"reported_result={activity.reported_result} is a claim",
                confidence="low",
                result_token=activity.reported_result,
                is_claim=True,
            )
        )
    return claims


class TimelineReconstructor:
    def eligible(self, observations: list[Observation], audit_at: datetime) -> list[Observation]:
        return [row for row in observations if row.eligible_at(audit_at)]

    def reconstruct(
        self,
        observations: list[Observation],
        audit_at: datetime,
        *,
        require_package: bool = True,
    ) -> list[ResourceState]:
        grouped: dict[tuple[str, str, str, str], list[Observation]] = {}
        rows = self.eligible(observations, audit_at) if require_package else observations
        for row in rows:
            if row.is_claim or row.presence not in {"present", "absent"}:
                continue
            if not row.resource_id:
                continue
            key = (row.system_id, row.resource_id, row.replica_role, row.replica_name or "")
            grouped.setdefault(key, []).append(row)
        states: list[ResourceState] = []
        for key, rows in grouped.items():
            states.append(_reduce(key, rows))
        states.sort(key=lambda item: (item.system_id, item.resource_id, item.replica_role, item.replica_name or ""))
        return states

    def drift(self, states: list[ResourceState]) -> list[ReplicationDrift]:
        grouped: dict[tuple[str, str], list[ResourceState]] = {}
        for state in states:
            grouped.setdefault((state.system_id, state.resource_id), []).append(state)
        found: list[ReplicationDrift] = []
        for (system_id, resource_id), rows in grouped.items():
            present = tuple(sorted({_label(row) for row in rows if row.presence == "present"}))
            absent = tuple(sorted({_label(row) for row in rows if row.presence == "absent"}))
            if present and absent:
                found.append(
                    ReplicationDrift(
                        system_id=system_id,
                        resource_id=resource_id,
                        present_on=present,
                        absent_on=absent,
                    )
                )
        found.sort(key=lambda item: (item.system_id, item.resource_id))
        return found

    def recreation_risks(self, states: list[ResourceState]) -> list[RecreationRisk]:
        risks: list[RecreationRisk] = []
        for state in states:
            if state.presence != "present" or not state.evidence_id:
                continue
            if state.flow_enabled is True:
                risks.append(
                    RecreationRisk(
                        system_id=state.system_id,
                        resource_id=state.resource_id,
                        kind="active_flow",
                        evidence_id=state.evidence_id,
                        observed_at=state.observed_at,
                        detail="latest eligible observation shows the data flow enabled",
                    )
                )
            if state.restore_blocked is False:
                risks.append(
                    RecreationRisk(
                        system_id=state.system_id,
                        resource_id=state.resource_id,
                        kind="restore",
                        evidence_id=state.evidence_id,
                        observed_at=state.observed_at,
                        detail="latest eligible observation shows restore is not blocked",
                    )
                )
        risks.sort(key=lambda item: (item.kind, item.system_id, item.resource_id))
        return risks


def _label(state: ResourceState) -> str:
    return state.replica_name or state.replica_role


def _reduce(key: tuple[str, str, str, str], rows: list[Observation]) -> ResourceState:
    def sort_key(row: Observation) -> tuple[datetime, datetime, str]:
        observed = row.observed_at or row.captured_at
        captured = row.captured_at or observed
        assert observed is not None and captured is not None
        return (observed, captured, row.source_locator)

    ordered = sorted(rows, key=sort_key)
    latest_time = sort_key(ordered[-1])[:2]
    latest = [row for row in ordered if sort_key(row)[:2] == latest_time]
    presences = {row.presence for row in latest}
    conflict = len(presences) > 1
    winner = sorted(latest, key=lambda row: row.source_locator)[-1]
    limitations = tuple(dict.fromkeys(row.limitations for row in latest if row.limitations))
    if conflict:
        limitations = limitations + ("conflicting presence at the same observation time",)
    return ResourceState(
        system_id=key[0],
        resource_id=key[1],
        replica_role=key[2],
        replica_name=key[3] or None,
        presence="conflict" if conflict else winner.presence,
        evidence_id=None if conflict else winner.evidence_id,
        observed_at=winner.observed_at,
        captured_at=winner.captured_at,
        record_type=winner.record_type,
        identifiers_exposed=winner.identifiers_exposed,
        anonymized=winner.anonymized,
        redacted=winner.redacted,
        flow_enabled=winner.flow_enabled,
        restore_blocked=winner.restore_blocked,
        retention_until=winner.retention_until,
        unresolved_conflict=conflict,
        limitations=limitations,
        confidence="low" if conflict else winner.confidence,
        linkable=bool(
            winner.identifiers.user_ids
            or winner.identifiers.emails
            or winner.identifiers.phones
            or winner.identifiers.email_hashes
            or winner.identifiers.names
        ),
    )
