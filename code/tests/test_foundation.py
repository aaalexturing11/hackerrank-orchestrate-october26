"""Foundation tests for ingestion, identity, time, classification, and scoring."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.engine.classifier import RequestIntent, classify_request
from code.engine.step_builder import (
    finding,
    remediation,
    sort_steps,
    validate_case,
    validate_header,
    verification,
)
from code.evaluation.fixtures import (
    T0,
    T1,
    exposed_tombstone_observation,
    exposed_tombstone_steps,
    non_deletion_output,
    non_deletion_text,
    replica_observations,
)
from code.evaluation.main import score_sample_against_itself
from code.evaluation.score import score_rows
from code.evaluation.usage import UsageLedger
from code.identity.resolver import IdentityResolver, fold_email, phone_digits
from code.ingestion.csv_loader import _require_columns, load_dataset
from code.ingestion.evidence_registry import EvidenceRegistry
from code.models import ActivityRecord, IdentityChange, IdentitySnapshot, ParseResult
from code.timeline.reconstructor import TimelineReconstructor, activities_as_claims

UTC = timezone.utc


class FoundationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_dataset()
        cls.resolver = IdentityResolver.from_dataset(cls.dataset)
        cls.results = EvidenceRegistry(cls.dataset, ROOT / "dataset").parse_all()
        cls.by_file = {result.file_id: result for result in cls.results}

    def test_dataset_loads_every_request(self) -> None:
        self.assertEqual(len(self.dataset.requests), 518)
        self.assertEqual(len(self.dataset.requests_by_id), 518)
        self.assertEqual(self.dataset.duplicate_ids, {})
        self.assertTrue(all(item.audit_at.tzinfo is UTC for item in self.dataset.requests))

    def test_leading_zeros_stay_strings(self) -> None:
        self.assertIn("search_052", self.dataset.activities_by_resource)
        self.assertNotIn("search_52", self.dataset.activities_by_resource)
        self.assertIsInstance(self.dataset.activities_by_resource["search_052"][0].resource_id, str)

    def test_missing_column_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _require_columns(["case_id"], ("case_id", "email"), "example.csv")

    def test_historical_email_resolves_and_future_email_is_excluded(self) -> None:
        identities = self.dataset.identities_by_user
        change = next(
            row
            for row in self.dataset.audit_log
            if row.field_name == "email"
            and row.old_value
            and fold_email(row.old_value) != fold_email(identities[row.user_id].email)
        )
        resolved = self.resolver.resolve_email(change.old_value)
        self.assertEqual(resolved.status, "unique")
        self.assertEqual(resolved.user_id, change.user_id)
        before = change.event_time - timedelta(seconds=1)
        aliases = self.resolver.aliases_at(change.user_id, before)
        self.assertNotIn(fold_email(change.new_value), aliases.emails)
        self.assertIn(fold_email(change.old_value), aliases.emails)

    def test_shared_name_does_not_join_users(self) -> None:
        by_name: dict[str, list[str]] = {}
        for snapshot in self.dataset.identities:
            by_name.setdefault(snapshot.name.casefold(), []).append(snapshot.user_id)
        collisions = [users for users in by_name.values() if len(users) > 1]
        self.assertGreaterEqual(len(collisions), 1)
        for users in collisions:
            emails = [self.dataset.identities_by_user[user_id].email for user_id in users]
            resolved = [self.resolver.resolve_email(email).user_id for email in emails]
            self.assertEqual(len(set(resolved)), len(users))

    def test_phone_normalization_and_casefold(self) -> None:
        snapshot = next(row for row in self.dataset.identities if any(ch in row.phone for ch in " -()"))
        compact = "+" + phone_digits(snapshot.phone)
        aliases = self.resolver.aliases_at(snapshot.user_id, datetime(2030, 1, 1, tzinfo=UTC))
        self.assertIn(phone_digits(compact), aliases.phones)
        self.assertEqual(
            self.resolver.resolve_email(snapshot.email.upper()).user_id,
            snapshot.user_id,
        )

    def test_ambiguous_email_is_not_joined(self) -> None:
        first = IdentitySnapshot("user_a", "A", "shared@example.com", "+1 202 555 0101", "a" * 64, datetime(2026, 1, 1, tzinfo=UTC))
        second = IdentitySnapshot("user_b", "A", "shared@example.com", "+1 202 555 0102", "b" * 64, datetime(2026, 1, 1, tzinfo=UTC))
        resolver = IdentityResolver(snapshots=[first, second], changes=[])
        result = resolver.resolve_email("Shared@example.com")
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.user_id)

    def test_future_alias_rolls_back(self) -> None:
        snapshot = IdentitySnapshot(
            "user_roll",
            "Roll",
            "new@example.com",
            "+1 202 555 0199",
            "c" * 64,
            datetime(2026, 6, 2, tzinfo=UTC),
        )
        change = IdentityChange(
            "audit_roll",
            "user_roll",
            datetime(2026, 6, 2, tzinfo=UTC),
            "email",
            "old@example.com",
            "new@example.com",
        )
        resolver = IdentityResolver(snapshots=[snapshot], changes=[change])
        before = datetime(2026, 6, 1, tzinfo=UTC)
        aliases = resolver.aliases_at("user_roll", before)
        self.assertIn("old@example.com", aliases.emails)
        self.assertNotIn("new@example.com", aliases.emails)
        self.assertEqual(resolver.resolve_email("new@example.com", audit_at=before).status, "unresolved")

    def test_delete_claim_does_not_invent_account_link(self) -> None:
        audit_at = datetime(2026, 12, 31, tzinfo=UTC)
        resources = self.resolver.resources_for_user("user_01", audit_at, [])
        self.assertNotIn(("account_service", "account_001"), resources)
        claim = activities_as_claims([self.dataset.activities_by_id["activity_3342"]])[0]
        self.assertTrue(claim.is_claim)
        self.assertEqual(claim.presence, "unknown")
        self.assertEqual(TimelineReconstructor().reconstruct([claim], audit_at), [])

    def test_classifier_distinguishes_deletion_and_other_requests(self) -> None:
        self.assertIs(classify_request("Please delete my account and all personal data.").intent, RequestIntent.DELETION)
        self.assertIs(
            classify_request(
                "The privacy page still says my request failed. Please inspect the actual systems and tell me whether the account and identifiable analytics data have already been removed."
            ).intent,
            RequestIntent.DELETION,
        )
        self.assertIs(
            classify_request(
                "Please check the latest state and confirm that the profile is gone and that remaining records cannot identify me."
            ).intent,
            RequestIntent.DELETION,
        )
        self.assertIs(classify_request("I would like the account associated with this address to be erased.").intent, RequestIntent.DELETION)
        self.assertIs(
            classify_request("Solicito a exclusão permanente da conta associada a este e-mail.").intent,
            RequestIntent.DELETION,
        )
        self.assertIs(
            classify_request("Delete my records and don't leave copies behind.").intent,
            RequestIntent.DELETION,
        )
        self.assertIs(
            classify_request("Please send a copy of the invoices on this account.").intent,
            RequestIntent.NON_DELETION,
        )
        self.assertIs(
            classify_request("The personal data must not be deleted.").intent,
            RequestIntent.NON_DELETION,
        )
        self.assertIs(
            classify_request("Please correct my address. It is out of date.").intent,
            RequestIntent.NON_DELETION,
        )
        self.assertIs(
            classify_request("I can't access my profile and need a password reset.").intent,
            RequestIntent.NON_DELETION,
        )
        self.assertIs(classify_request("Hello, can you tell me the shop hours?").intent, RequestIntent.AMBIGUOUS)
        self.assertIs(
            classify_request(
                "Please remove me from marketing lists only. I still want receipts and service messages for this account."
            ).intent,
            RequestIntent.NON_DELETION,
        )
        intents = {classify_request(row.request_text).intent for row in self.dataset.requests}
        self.assertTrue(intents <= {RequestIntent.DELETION, RequestIntent.NON_DELETION, RequestIntent.AMBIGUOUS})

    def test_sql_replica_absence_is_scoped(self) -> None:
        result = self.by_file["evidence_54"]
        self.assertEqual(result.status, "parsed")
        present = _match(result, "account_005", "present")
        absent = _match(result, "account_005", "absent")
        self.assertTrue(any(row.replica_role == "failover" for row in present))
        self.assertTrue(any(row.replica_role == "primary" for row in absent))
        self.assertFalse(any(row.resource_id == "account_001" for row in result.observations))
        captured = self.dataset.evidence_by_id["evidence_54"].captured_at
        timeline = TimelineReconstructor()
        at_capture = timeline.reconstruct(result.observations, captured)
        self.assertTrue(any(row.resource_id == "account_005" and row.presence == "present" for row in at_capture))
        earlier = timeline.reconstruct(result.observations, captured - timedelta(seconds=1))
        self.assertFalse(any(row.resource_id == "account_005" for row in earlier))

    def test_post_audit_replica_evidence_is_excluded(self) -> None:
        timeline = TimelineReconstructor()
        states = timeline.reconstruct(replica_observations(), T1)
        self.assertTrue(any(row.replica_role == "failover" and row.presence == "present" for row in states))
        self.assertTrue(any(row.replica_role == "primary" and row.presence == "absent" for row in states))
        self.assertTrue(timeline.drift(states))
        self.assertFalse(any(row.evidence_id == "fixture_later_file" for row in states))
        after = timeline.reconstruct(replica_observations(), T1.replace(year=2027))
        failover = [row for row in after if row.replica_role == "failover"]
        self.assertEqual([row.presence for row in failover], ["absent"])

    def test_logs_distinguish_absence_from_remaining_rows(self) -> None:
        absent = _match(self.by_file["evidence_01"], "account_5762", "absent")
        self.assertEqual(len(absent), 1)
        self.assertEqual(absent[0].result_token, "HTTP_404")
        present = _match(self.by_file["evidence_61"], "support_002", "present")
        self.assertGreaterEqual(len(present), 1)
        readback = self.by_file["evidence_94"]
        self.assertEqual(readback.status, "parsed")
        flow = _one(readback, "data_flow_4713")
        self.assertEqual(flow.flow_enabled, False)
        self.assertIn("user_49", flow.identifiers.user_ids)
        self.assertNotIn("null", flow.identifiers.emails)
        backup = _one(readback, "backup_7809")
        self.assertEqual(backup.restore_blocked, True)
        self.assertEqual(_one(readback, "account_2064").presence, "absent")
        self.assertIn("charlotte.wright@outlook.com", _one(readback, "account_2064").identifiers.emails)
        self.assertEqual(_one(readback, "search_4262").presence, "present")
        self.assertEqual(_one(readback, "analytics_037").resource_id, "analytics_037")

    def test_alternate_log_dialects_and_empty_sql(self) -> None:
        bracket = self.by_file["evidence_16"]
        self.assertEqual(bracket.status, "parsed")
        missing = _one(bracket, "account_7947")
        self.assertEqual(missing.presence, "absent")
        self.assertIn("l.nascimento40@gmail.com", missing.identifiers.emails)
        pipe = self.by_file["evidence_21"]
        self.assertEqual(pipe.status, "parsed")
        exported = _one(pipe, "export_5351")
        self.assertEqual(exported.presence, "present")
        self.assertEqual(exported.record_type, "USER_EXPORT")
        cloud = self.by_file["evidence_25"]
        hit = _one(cloud, "search_021")
        self.assertEqual(hit.presence, "present")
        self.assertEqual(hit.resource_id, "search_021")
        self.assertIn("mrios9507.jr@fastmail.com", hit.identifiers.emails)
        empty = self.by_file["evidence_90"]
        self.assertEqual(empty.observations, [])
        self.assertTrue(any("not proof of absence" in warning for warning in empty.warnings))

    def test_documents_extract_without_cross_joining_orders(self) -> None:
        handover = _result_for_suffix(self.results, "customer_account_handover_20261001.txt")
        search = _one(handover, "search_052")
        self.assertEqual(search.presence, "present")
        self.assertEqual(search.resource_id, "search_052")
        security = self.by_file["evidence_55"]
        self.assertEqual(security.status, "parsed")
        audit = _one(security, "audit_record_003")
        self.assertIn("user_03", audit.identifiers.user_ids)
        attachment = self.by_file["evidence_58"]
        support = _one(attachment, "support_001")
        self.assertIn("priya.raman@gmail.com", support.identifiers.emails)
        statement = self.by_file["evidence_18"]
        self.assertTrue(any("user_18" in row.identifiers.user_ids for row in statement.observations))
        register = self.by_file["evidence_27"]
        self.assertEqual(register.status, "parsed")
        self.assertGreater(len({row.resource_id for row in register.observations}), 1)
        self.assertTrue(all(len(row.identifiers.user_ids) <= 1 for row in register.observations))
        self.assertTrue(any(row.record_type == "FINANCE_RETENTION_NOTE" for row in register.observations))

    def test_every_evidence_file_is_explicitly_classified(self) -> None:
        self.assertEqual(len(self.results), len(self.dataset.evidence))
        failed = [row.file_id for row in self.results if row.status == "failed"]
        pending = [row.file_id for row in self.results if row.status == "requires_processing"]
        self.assertEqual(failed, [])
        self.assertEqual(pending, [])
        self.assertEqual(self.by_file["evidence_04"].status, "parsed")
        self.assertTrue(any(row.resource_id == "account_5762" for row in self.by_file["evidence_04"].observations))

    def test_validator_rejects_illegal_sequences(self) -> None:
        self.assertEqual(validate_header(["case_id", "email"]), [validate_header(["case_id", "email"])[0]])
        self.assertEqual(validate_header(["case_id", "deletion_status", "steps_json"]), [])
        bad_pair = finding(
            system_id="account_service",
            resource_id="account_1",
            operation="REPORT_REMAINING_RECORD",
            evidence_id="evidence_01",
        )
        bad_pair = type(bad_pair)(1, bad_pair.phase, bad_pair.system_id, bad_pair.resource_id, bad_pair.operation, "ABSENT", bad_pair.evidence_id)
        self.assertTrue(any(issue.code == "bad_pair" for issue in validate_case(deletion_status="INCOMPLETE", steps=[bad_pair])))
        unordered = [
            verification(system_id="account_service", resource_id="account_1", operation="VERIFY_RECORD_ABSENT", evidence_id="", step_no=1),
            finding(system_id="account_service", resource_id="account_1", operation="REPORT_REMAINING_RECORD", evidence_id="evidence_01", step_no=2),
        ]
        self.assertTrue(any(issue.code == "order" for issue in validate_case(deletion_status="INCOMPLETE", steps=unordered)))
        numbered = sort_steps(
            [
                finding(system_id="search_service", resource_id="search_1007", operation="REPORT_REMAINING_RECORD", evidence_id="evidence_01"),
                finding(system_id="search_service", resource_id="search_899", operation="REPORT_REMAINING_RECORD", evidence_id="evidence_01"),
            ]
        )
        self.assertEqual([step.resource_id for step in numbered], ["search_1007", "search_899"])
        numeric = sort_steps(numbered, resource_sort="numeric")
        self.assertEqual([step.resource_id for step in numeric], ["search_899", "search_1007"])
        gapped = [AuditStepFix(2)]
        self.assertTrue(any(issue.code == "numbering" for issue in validate_case(deletion_status="INCOMPLETE", steps=gapped)))
        dirty = [remediation(system_id="account_service", resource_id="account_1", operation="DELETE_RECORD", step_no=1)]
        dirty[0] = type(dirty[0])(1, "REMEDIATION", "account_service", "account_1", "DELETE_RECORD", "ABSENT", "evidence_01")
        self.assertTrue(any(issue.code == "evidence_present" for issue in validate_case(deletion_status="INCOMPLETE", steps=dirty)))
        empty_complete = [verification(system_id="account_service", resource_id="account_1", operation="VERIFY_RECORD_ABSENT", evidence_id="", step_no=1)]
        self.assertTrue(any(issue.code == "evidence_empty" for issue in validate_case(deletion_status="COMPLETE", steps=empty_complete)))
        self.assertTrue(validate_case(deletion_status="NOT_APPLICABLE", steps=empty_complete))
        known = {"evidence_01"}
        late = datetime(2026, 1, 1, tzinfo=UTC)
        early = datetime(2025, 1, 1, tzinfo=UTC)
        step = verification(system_id="account_service", resource_id="account_1", operation="VERIFY_RECORD_ABSENT", evidence_id="evidence_01", step_no=1)
        self.assertTrue(
            any(
                issue.code == "evidence_after_audit"
                for issue in validate_case(
                    deletion_status="COMPLETE",
                    steps=[step],
                    known_evidence_ids=known,
                    evidence_times={"evidence_01": late},
                    audit_at=early,
                )
            )
        )

    def test_public_sample_validates_and_scores_itself(self) -> None:
        import csv

        sample_path = ROOT / "dataset" / "sample_output.csv"
        with sample_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        known = {row.file_id for row in self.dataset.evidence}
        known.update(row.activity_id for row in self.dataset.activities)
        known.update(row.audit_id for row in self.dataset.audit_log)
        problems = []
        for row in rows:
            from code.engine.step_builder import steps_from_json

            issues = validate_case(
                deletion_status=row["deletion_status"],
                steps=steps_from_json(row["steps_json"]),
                known_evidence_ids=known,
            )
            if issues:
                problems.append((row["case_id"], [(issue.code, issue.message) for issue in issues]))
        self.assertEqual(problems, [])
        report = score_sample_against_itself()
        self.assertEqual(report.cases, 32)
        self.assertEqual(report.status_correct, 32)
        self.assertEqual(report.exact_rows, 32)
        self.assertEqual(report.sequence_exact, 32)
        self.assertEqual(report.field_matches, report.field_total)
        self.assertEqual(report.failures, [])
        self.assertEqual(report.field_mismatches, [])
        self.assertEqual(report.status_accuracy, 1.0)
        broken = [dict(rows[0])]
        broken[0]["deletion_status"] = "INCOMPLETE"
        failed = score_rows(rows, broken)
        self.assertLess(failed.status_correct, failed.cases)

    def test_contract_fixtures(self) -> None:
        self.assertIs(classify_request(non_deletion_text()).intent, RequestIntent.NON_DELETION)
        expected = non_deletion_output()
        self.assertEqual(expected["steps_json"], "[]")
        self.assertEqual(validate_case(deletion_status=expected["deletion_status"], steps=[]), [])
        tombstone = exposed_tombstone_observation()
        self.assertTrue(tombstone.identifiers_exposed)
        self.assertTrue(tombstone.identifiers.emails)
        self.assertIn("user_9001", tombstone.identifiers.user_ids)
        issues = validate_case(
            deletion_status="INCOMPLETE",
            steps=exposed_tombstone_steps(),
            known_evidence_ids={"fixture_tombstone_file"},
        )
        self.assertEqual(issues, [])
        self.assertEqual([step.evidence_id for step in exposed_tombstone_steps() if step.phase != "FINDING"], ["", "", "", ""])

    def test_usage_ledger_starts_at_zero(self) -> None:
        self.assertEqual(UsageLedger().summary()["model_calls"], 0)


def _match(result: ParseResult, resource_id: str, presence: str):
    return [row for row in result.observations if row.resource_id == resource_id and row.presence == presence]


def _one(result: ParseResult, resource_id: str):
    rows = [row for row in result.observations if row.resource_id == resource_id]
    if len(rows) != 1:
        raise AssertionError(f"{result.file_id} {resource_id} matched {len(rows)} observations")
    return rows[0]


def _result_for_suffix(results: list[ParseResult], suffix: str) -> ParseResult:
    matches = [row for row in results if row.path.replace("\\", "/").endswith(suffix)]
    if len(matches) != 1:
        raise AssertionError(f"{suffix} matched {len(matches)} files")
    return matches[0]


def AuditStepFix(step_no: int):
    return finding(
        system_id="account_service",
        resource_id="account_1",
        operation="REPORT_REMAINING_RECORD",
        evidence_id="evidence_01",
        step_no=step_no,
    )


if __name__ == "__main__":
    unittest.main()
