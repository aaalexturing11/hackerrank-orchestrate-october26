"""Policy, identity-link, and step-construction regressions.

These tests use synthetic records and packaged image facts. They do not read
sample answers.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from code.engine.planner import DeletionPlanner
from code.evaluation.missing_steps import resource_in_payload
from code.engine.systems import canonical_system
from code.identity.resolver import IdentityResolver
from code.ingestion.image_facts import IMAGE_FACTS
from code.ingestion.json_parser import parse_json_file
from code.ingestion.log_parser import parse_log_file
from code.ingestion.sql_parser import parse_sql_file
from code.models import DeletionRequest, EvidenceFile, IdentifierBag, IdentitySnapshot, Observation, ResourceState
from code.policy.decide import category_for, decide

UTC = timezone.utc
AUDIT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
REQUESTED = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _request(text: str = "Please delete my account and personal data.") -> DeletionRequest:
    return DeletionRequest(
        case_id="case_synth",
        email="ada@example.com",
        requested_at=REQUESTED,
        reported_status="COMPLETE",
        reported_at=datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        audit_at=AUDIT,
        request_text=text,
    )


def _resolver() -> IdentityResolver:
    return IdentityResolver(
        snapshots=[
            IdentitySnapshot(
                user_id="user_ada",
                name="Ada Example",
                email="ada@example.com",
                phone="",
                email_hash="",
                updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
        changes=[],
    )


def _observation(**overrides) -> Observation:
    values = dict(
        evidence_id="evidence_synth",
        system_id="analytics_identity_store",
        resource_id="analytics_901",
        observed_at=datetime(2026, 9, 10, tzinfo=UTC),
        captured_at=datetime(2026, 9, 10, tzinfo=UTC),
        record_type="ANALYTICS_PROFILE",
        replica_role="primary",
        replica_name=None,
        presence="present",
        identifiers=IdentifierBag(emails=("ada@example.com",)),
        identifiers_exposed=True,
        anonymized=False,
        redacted=None,
        flow_enabled=None,
        restore_blocked=None,
        retention_until=None,
        result_token=None,
        is_claim=False,
        source_locator="synthetic",
        limitations="",
        confidence="high",
    )
    values.update(overrides)
    return Observation(**values)


def _state(**overrides) -> ResourceState:
    values = dict(
        system_id="identity_service",
        resource_id="tombstone_1",
        replica_role="primary",
        replica_name=None,
        presence="present",
        evidence_id="evidence_synth",
        observed_at=AUDIT,
        captured_at=AUDIT,
        record_type="ACCOUNT_TOMBSTONE",
        identifiers_exposed=False,
        anonymized=None,
        redacted=True,
        flow_enabled=None,
        restore_blocked=None,
        retention_until=None,
        unresolved_conflict=False,
        limitations=(),
        confidence="high",
        linkable=True,
    )
    values.update(overrides)
    return ResourceState(**values)


class PolicyTests(unittest.TestCase):
    def test_unknown_store_name_is_not_fuzzy_matched(self) -> None:
        self.assertEqual(canonical_system("analytics_identity_store", "analytics_901"), "analytics_identity_store")
        self.assertEqual(canonical_system("support_replica", "support_002"), "support_platform")
        self.assertEqual(canonical_system("account_failover_replica", "account_005"), "account_failover_replica")

    def test_category_system_replaces_noncanonical_store(self) -> None:
        decision = DeletionPlanner(_resolver(), [_observation()], []).audit(_request())
        systems = {step.system_id for step in decision.steps}
        self.assertIn("analytics_platform", systems)
        self.assertNotIn("analytics_identity_store", systems)

    def test_tombstone_with_only_stable_reference_is_compliant(self) -> None:
        treatment = decide(_state(), AUDIT)
        self.assertIsNotNone(treatment)
        assert treatment is not None
        self.assertTrue(treatment.compliant)
        self.assertEqual(treatment.verification_operation, "VERIFY_RECORD_REDACTED")
        self.assertIsNone(treatment.finding_operation)

    def test_retained_security_log_is_not_a_violation(self) -> None:
        treatment = decide(
            _state(
                system_id="security_service",
                resource_id="audit_record_1",
                record_type="SECURITY_AUDIT_LOG",
                identifiers_exposed=False,
                redacted=None,
                retention_until=datetime(2031, 12, 31, tzinfo=UTC),
            ),
            AUDIT,
        )
        self.assertIsNotNone(treatment)
        assert treatment is not None
        self.assertTrue(treatment.compliant)
        self.assertEqual(treatment.verification_operation, "VERIFY_RECORD_PRESENT")

    def test_finance_note_is_not_a_legal_hold(self) -> None:
        self.assertIsNone(category_for("FINANCE_RETENTION_NOTE"))
        self.assertEqual(category_for("retained_order_records"), "LEGAL_HOLD_RECORD")

    def test_nested_legal_hold_keeps_subject_reference(self) -> None:
        script = """
        CREATE TABLE customer_data_primary (
            resource_id TEXT, origin_system TEXT, collection_name TEXT, record_json TEXT, updated_at TEXT
        );
        INSERT INTO customer_data_primary VALUES (
            'legal_hold_8017', 'legal_service', 'retained_order_records',
            '{"subject_reference":"user_259","order_reference":"ORD-20268017"}',
            '2026-04-24T08:00:00Z'
        );
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hold.sql"
            path.write_text(script, encoding="utf-8")
            evidence = EvidenceFile("evidence_hold", "hold.sql", "sql", datetime(2026, 4, 24, tzinfo=UTC))
            parsed = parse_sql_file(evidence, path)
        self.assertEqual(parsed.observations[0].record_type, "LEGAL_HOLD_RECORD")
        self.assertIn("user_259", parsed.observations[0].identifiers.user_ids)

    def test_absence_before_the_request_is_not_audit_time_proof(self) -> None:
        stale = _observation(
            system_id="account_service",
            resource_id="account_6523",
            record_type="USER_PROFILE",
            presence="absent",
            observed_at=datetime(2026, 3, 10, tzinfo=UTC),
            captured_at=datetime(2026, 3, 10, tzinfo=UTC),
            identifiers_exposed=False,
        )
        decision = DeletionPlanner(_resolver(), [stale], []).audit(_request())
        self.assertEqual(decision.steps, [])

    def test_packaged_image_facts_keep_distinct_search_rows(self) -> None:
        expected = {
            "evidence_04",
            "evidence_09",
            "evidence_14",
            "evidence_19",
            "evidence_23",
            "evidence_28",
            "evidence_32",
            "evidence_37",
            "evidence_42",
            "evidence_46",
            "evidence_60",
        }
        self.assertEqual(set(IMAGE_FACTS), expected)
        rows = {row["resource_id"] for row in IMAGE_FACTS["evidence_09"]}
        self.assertEqual(rows, {"search_428", "search_1874"})

    def test_same_trace_keeps_a_lookup_key_when_the_completion_says_null(self) -> None:
        text = "\n".join(
            [
                "2026-09-10T00:00:00Z level=DEBUG service=account_service trace_id=rb-1 event=profile_lookup_started resource_id=account_10 lookup_key=ada@example.com",
                "2026-09-10T00:00:01Z level=INFO service=account_service trace_id=rb-1 event=profile_lookup_completed resource_id=account_10 lookup_key=null rows=0 http_status=404",
                "2026-09-10T00:00:02Z level=DEBUG service=analytics_platform trace_id=rb-2 event=analytics_profile_read_started resource_id=analytics_10 lookup_key=null",
                "2026-09-10T00:00:03Z level=INFO service=analytics_platform trace_id=rb-2 event=analytics_profile_read_completed resource_id=analytics_10 email=null",
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.log"
            path.write_text(text, encoding="utf-8")
            evidence = EvidenceFile("evidence_trace", "trace.log", "log", AUDIT)
            parsed = parse_log_file(evidence, path)
        by_resource = {row.resource_id: row for row in parsed.observations}
        self.assertIn("ada@example.com", by_resource["account_10"].identifiers.emails)
        self.assertTrue(by_resource["analytics_10"].identifiers.is_empty())

    def test_empty_profile_collection_does_not_invent_an_account(self) -> None:
        payload = """
        {"snapshots":[{"captured_at":"2026-09-15T12:00:00Z","data_store":"account_service","collection":"customer_profiles","records":[]}]}
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.json"
            path.write_text(payload, encoding="utf-8")
            evidence = EvidenceFile("evidence_empty", "empty.json", "json", AUDIT)
            parsed = parse_json_file(evidence, path)
        self.assertEqual(parsed.observations, [])

    def test_sql_omission_requires_the_id_on_the_other_table(self) -> None:
        script = """
        CREATE TABLE customer_profiles_primary (resource_id TEXT, email TEXT, updated_at TEXT);
        CREATE TABLE customer_profiles_failover_replica (resource_id TEXT, email TEXT, updated_at TEXT);
        INSERT INTO customer_profiles_primary VALUES ('account_a','ada@example.com','2026-09-02T00:00:00Z');
        INSERT INTO customer_profiles_failover_replica VALUES ('account_a','ada@example.com','2026-09-02T00:00:00Z');
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scope.sql"
            path.write_text(script, encoding="utf-8")
            evidence = EvidenceFile("evidence_scope", "scope.sql", "sql", AUDIT)
            parsed = parse_sql_file(evidence, path)
        self.assertEqual({row.resource_id for row in parsed.observations}, {"account_a"})

    def test_null_identifier_row_is_not_joined_through_a_shared_file(self) -> None:
        identified = _observation(
            resource_id="account_10",
            system_id="account_service",
            record_type="USER_PROFILE",
            presence="absent",
        )
        anonymous = _observation(
            resource_id="analytics_10",
            system_id="analytics_platform",
            record_type="ANALYTICS_PROFILE",
            identifiers=IdentifierBag(),
            identifiers_exposed=False,
            anonymized=True,
        )
        decision = DeletionPlanner(_resolver(), [identified, anonymous], []).audit(_request())
        self.assertEqual([step.resource_id for step in decision.steps], ["account_10"])

    def test_resource_search_does_not_match_a_longer_id(self) -> None:
        payload = b'resource_id="account_41038"'
        self.assertFalse(resource_in_payload("account_410", payload))
        self.assertTrue(resource_in_payload("account_41038", payload))


if __name__ == "__main__":
    unittest.main()
