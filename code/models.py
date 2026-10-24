"""Normalized records used by the deletion-audit foundation.

Observations keep provenance. A missing observation is not an absence proof.
An activity `reported_result` stays a claim until a non-claim observation
establishes the resource state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class DeletionRequest:
    case_id: str
    email: str
    requested_at: datetime
    reported_status: str
    reported_at: datetime
    audit_at: datetime
    request_text: str


@dataclass(frozen=True)
class IdentitySnapshot:
    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    updated_at: datetime


@dataclass(frozen=True)
class IdentityChange:
    audit_id: str
    user_id: str
    event_time: datetime
    field_name: str
    old_value: str
    new_value: str


@dataclass(frozen=True)
class ActivityRecord:
    activity_id: str
    event_time: datetime
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    data_category: str
    condition: str
    required_action: str


@dataclass(frozen=True)
class EvidenceFile:
    file_id: str
    file_path: str
    origin: str
    captured_at: datetime


@dataclass(frozen=True)
class IdentifierBag:
    """Identifiers found on one observation. Names are stored and never used as join keys."""

    emails: tuple[str, ...] = ()
    phones: tuple[str, ...] = ()
    email_hashes: tuple[str, ...] = ()
    user_ids: tuple[str, ...] = ()
    names: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (self.emails or self.phones or self.email_hashes or self.user_ids)


@dataclass(frozen=True)
class Observation:
    evidence_id: str
    system_id: str
    resource_id: str
    observed_at: Optional[datetime]
    captured_at: Optional[datetime]
    record_type: Optional[str]
    replica_role: str
    replica_name: Optional[str]
    presence: str
    identifiers: IdentifierBag
    identifiers_exposed: Optional[bool]
    anonymized: Optional[bool]
    redacted: Optional[bool]
    flow_enabled: Optional[bool]
    restore_blocked: Optional[bool]
    retention_until: Optional[datetime]
    result_token: Optional[str]
    is_claim: bool
    source_locator: str
    limitations: str
    confidence: str
    sole_subject: Optional[bool] = None
    shared_context: Optional[bool] = None

    def eligible_at(self, audit_at: datetime) -> bool:
        """True when both the file capture and the inner observation are at or before audit_at."""
        if self.captured_at is not None and self.captured_at > audit_at:
            return False
        if self.observed_at is not None and self.observed_at > audit_at:
            return False
        if self.captured_at is None and self.observed_at is None:
            return False
        return True


@dataclass(frozen=True)
class ResourceState:
    system_id: str
    resource_id: str
    replica_role: str
    replica_name: Optional[str]
    presence: str
    evidence_id: Optional[str]
    observed_at: Optional[datetime]
    captured_at: Optional[datetime]
    record_type: Optional[str]
    identifiers_exposed: Optional[bool]
    anonymized: Optional[bool]
    redacted: Optional[bool]
    flow_enabled: Optional[bool]
    restore_blocked: Optional[bool]
    retention_until: Optional[datetime]
    unresolved_conflict: bool
    limitations: tuple[str, ...]
    confidence: str
    linkable: Optional[bool] = None


@dataclass(frozen=True)
class ReplicationDrift:
    system_id: str
    resource_id: str
    present_on: tuple[str, ...]
    absent_on: tuple[str, ...]


@dataclass(frozen=True)
class RecreationRisk:
    system_id: str
    resource_id: str
    kind: str
    evidence_id: str
    observed_at: Optional[datetime]
    detail: str


@dataclass(frozen=True)
class AuditStep:
    step_no: int
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "step_no": self.step_no,
            "phase": self.phase,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "state": self.state,
            "evidence_id": self.evidence_id,
        }

    def comparable(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.phase,
            self.system_id,
            self.resource_id,
            self.operation,
            self.state,
            self.evidence_id,
        )


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    step_no: Optional[int] = None


@dataclass
class ParseResult:
    file_id: str
    path: str
    kind: str
    status: str
    observations: list[Observation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IdentityLink:
    evidence_id: str
    event_time: datetime
    system_id: str
    resource_id: str
    email: Optional[str]
    user_id: Optional[str]
    sole_subject: bool
    source: str
