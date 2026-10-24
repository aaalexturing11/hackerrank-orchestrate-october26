"""Audit entry points.

`FoundationAuditor.build_context` classifies the request, resolves identity,
and reconstructs eligible state. `DeletionAuditor.audit` applies policy and
emits contract steps. Activity rows remain claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from code.engine.classifier import Classification, RequestIntent, classify_request
from code.engine.planner import AuditDecision, DeletionPlanner
from code.identity.resolver import AliasSet, IdentityResolver
from code.models import DeletionRequest, Observation, RecreationRisk, ReplicationDrift, ResourceState
from code.timeline.reconstructor import TimelineReconstructor


@dataclass
class AuditContext:
    case_id: str
    classification: Classification
    deletion_authorized: bool
    user_id: str | None
    identity_status: str
    aliases: AliasSet | None
    observations: list[Observation] = field(default_factory=list)
    states: list[ResourceState] = field(default_factory=list)
    drift: list[ReplicationDrift] = field(default_factory=list)
    recreation_risks: list[RecreationRisk] = field(default_factory=list)
    linked_resources: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class FoundationAuditor:
    def __init__(self, resolver: IdentityResolver, observations: list[Observation]) -> None:
        self.resolver = resolver
        self.observations = observations
        self.timeline = TimelineReconstructor()

    def build_context(self, request: DeletionRequest) -> AuditContext:
        classification = classify_request(request.request_text)
        authorized = classification.intent is RequestIntent.DELETION
        resolved = self.resolver.resolve_email(request.email, audit_at=request.audit_at)
        notes: list[str] = []
        if classification.intent is RequestIntent.AMBIGUOUS:
            notes.append("request text does not authorize deletion")
        if classification.intent is RequestIntent.NON_DELETION:
            notes.append("request text is a non-deletion request")
        aliases = None
        linked: list[tuple[str, str]] = []
        scoped: list[Observation] = []
        states: list[ResourceState] = []
        drift: list[ReplicationDrift] = []
        risks: list[RecreationRisk] = []
        if resolved.status == "unique" and resolved.user_id is not None:
            aliases = self.resolver.aliases_at(resolved.user_id, request.audit_at)
            linked = self.resolver.resources_for_user(resolved.user_id, request.audit_at, self.observations)
            linked_ids = {resource_id for _system, resource_id in linked}
            scoped = [
                row
                for row in self.observations
                if row.eligible_at(request.audit_at)
                and (
                    (row.resource_id and row.resource_id in linked_ids)
                    or aliases.intersects(row.identifiers)
                )
            ]
            states = self.timeline.reconstruct(scoped, request.audit_at)
            drift = self.timeline.drift(states)
            risks = self.timeline.recreation_risks(states)
        elif resolved.status == "ambiguous":
            notes.append("email maps to more than one user; no resources were joined")
        else:
            notes.append("email did not resolve to a user at audit_at")
        return AuditContext(
            case_id=request.case_id,
            classification=classification,
            deletion_authorized=authorized,
            user_id=resolved.user_id,
            identity_status=resolved.status,
            aliases=aliases,
            observations=scoped,
            states=states,
            drift=drift,
            recreation_risks=risks,
            linked_resources=linked,
            notes=notes,
        )


class DeletionAuditor(FoundationAuditor):
    """Policy decision over the foundation context.

    `activities` are claims and anchors. They do not override observations.
    """

    def __init__(self, resolver: IdentityResolver, observations: list[Observation], activities: list) -> None:
        super().__init__(resolver, observations)
        self.planner = DeletionPlanner(resolver, observations, activities)

    def audit(self, request: DeletionRequest) -> AuditDecision:
        return self.planner.audit(request)
