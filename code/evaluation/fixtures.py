"""Contract-derived fixtures. These are not production labels."""

from __future__ import annotations

from datetime import datetime, timezone

from code.engine.step_builder import finding, remediation, sort_steps, verification
from code.ingestion.normalize import bag_from_mapping, make_observation
from code.models import AuditStep, Observation

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
AFTER = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def non_deletion_text() -> str:
    return (
        "Please send a copy of the invoices on this account. "
        "The personal data must not be deleted, and the account must stay active."
    )


def non_deletion_output() -> dict[str, str]:
    return {"case_id": "fixture_non_deletion", "deletion_status": "NOT_APPLICABLE", "steps_json": "[]"}


def replica_observations() -> list[Observation]:
    """A failover row remains at audit time. A later file says the row is gone."""
    present = make_observation(
        evidence_id="fixture_replica_file",
        system_id="account_service",
        resource_id="account_fixture",
        observed_at=T0,
        captured_at=T0,
        record_type="USER_PROFILE",
        replica_role="failover",
        replica_name="customer_profiles_failover_replica",
        presence="present",
        identifiers=bag_from_mapping({"email": "fixture.user@example.com", "user_id": "user_9001"}),
        identifiers_exposed=True,
        source_locator="fixture:failover",
        limitations="paired snapshot row",
        confidence="high",
        result_token="ACTIVE",
    )
    primary_absent = make_observation(
        evidence_id="fixture_replica_file",
        system_id="account_service",
        resource_id="account_fixture",
        observed_at=T0,
        captured_at=T0,
        record_type="USER_PROFILE",
        replica_role="primary",
        replica_name="customer_profiles_primary",
        presence="absent",
        identifiers=bag_from_mapping({}),
        identifiers_exposed=None,
        source_locator="fixture:primary-omission",
        limitations="paired snapshot omission inside this file only",
        confidence="medium",
        result_token="PAIRED_OMISSION",
    )
    later_absent = make_observation(
        evidence_id="fixture_later_file",
        system_id="account_service",
        resource_id="account_fixture",
        observed_at=AFTER,
        captured_at=AFTER,
        record_type="USER_PROFILE",
        replica_role="failover",
        replica_name="customer_profiles_failover_replica",
        presence="absent",
        identifiers=bag_from_mapping({}),
        identifiers_exposed=None,
        source_locator="fixture:after-audit",
        limitations="captured after the audit",
        confidence="high",
        result_token="NOT_FOUND",
    )
    return [present, primary_absent, later_absent]


def exposed_tombstone_observation() -> Observation:
    return make_observation(
        evidence_id="fixture_tombstone_file",
        system_id="identity_service",
        resource_id="tombstone_fixture",
        observed_at=T1,
        captured_at=T1,
        record_type="ACCOUNT_TOMBSTONE",
        replica_role="unspecified",
        replica_name=None,
        presence="present",
        identifiers=bag_from_mapping(
            {
                "user_id": "user_9001",
                "email": "fixture.user@example.com",
                "phone": "+1 202 555 0100",
                "name": "Fixture User",
            }
        ),
        identifiers_exposed=True,
        source_locator="fixture:tombstone",
        limitations="tombstone still stores direct identifiers",
        confidence="high",
        result_token="DELETED",
        redacted=False,
    )


def exposed_tombstone_steps() -> list[AuditStep]:
    """Contract shape for an exposed tombstone when the account is already gone and the audit log remains.

    The stable user reference may stay. Direct identifiers must be redacted.
    Future checks use an empty evidence id because the case is incomplete.
    """
    steps = [
        finding(
            system_id="identity_service",
            resource_id="tombstone_fixture",
            operation="REPORT_EXPOSED_PII",
            evidence_id="fixture_tombstone_file",
        ),
        remediation(
            system_id="identity_service",
            resource_id="tombstone_fixture",
            operation="REDACT_RECORD",
        ),
        verification(
            system_id="account_service",
            resource_id="account_fixture",
            operation="VERIFY_RECORD_ABSENT",
            evidence_id="",
        ),
        verification(
            system_id="security_service",
            resource_id="audit_record_fixture",
            operation="VERIFY_RECORD_PRESENT",
            evidence_id="",
        ),
        verification(
            system_id="identity_service",
            resource_id="tombstone_fixture",
            operation="VERIFY_RECORD_REDACTED",
            evidence_id="",
        ),
    ]
    return sort_steps(steps)
