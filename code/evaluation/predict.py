"""Run the auditor on the public sample and score it afterwards.

Prediction does not read sample_output.csv. The comparison below is a separate step.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from code.config import dataset_dir, repo_root
from code.engine.auditor import DeletionAuditor
from code.engine.step_builder import steps_from_json, validate_case
from code.evaluation.missing_steps import explain_predictions
from code.evaluation.score import ScoreReport, format_report, score_rows
from code.identity.resolver import IdentityResolver
from code.ingestion.csv_loader import load_dataset, parse_utc
from code.ingestion.evidence_registry import EvidenceRegistry
from code.models import DeletionRequest


def predict_sample(root: Path | None = None) -> list[dict[str, str]]:
    logging.disable(logging.CRITICAL)
    base = root or dataset_dir()
    dataset = load_dataset(base)
    observations = [
        item for result in EvidenceRegistry(dataset, base).parse_all() for item in result.observations
    ]
    auditor = DeletionAuditor(
        IdentityResolver.from_dataset(dataset),
        observations,
        dataset.activities,
    )
    with (base / "sample_deletion_requests.csv").open(encoding="utf-8", newline="") as handle:
        requests = list(csv.DictReader(handle))
    rows: list[dict[str, str]] = []
    known = {item.file_id for item in dataset.evidence}
    known.update(item.activity_id for item in dataset.activities)
    known.update(item.audit_id for item in dataset.audit_log)
    for raw in requests:
        request = DeletionRequest(
            case_id=raw["case_id"],
            email=raw["email"],
            requested_at=parse_utc(raw["requested_at"], source="requested_at"),
            reported_status=raw["reported_status"],
            reported_at=parse_utc(raw["reported_at"], source="reported_at"),
            audit_at=parse_utc(raw["audit_at"], source="audit_at"),
            request_text=raw["request_text"],
        )
        decision = auditor.audit(request)
        payload = json.dumps([step.as_dict() for step in decision.steps], separators=(",", ":"))
        issues = validate_case(
            deletion_status=decision.deletion_status,
            steps=decision.steps,
            known_evidence_ids=known,
            evidence_times={item.file_id: item.captured_at for item in dataset.evidence},
            audit_at=request.audit_at,
        )
        if issues:
            raise RuntimeError(f"{request.case_id} invalid steps: {issues}")
        rows.append(
            {
                "case_id": decision.case_id,
                "deletion_status": decision.deletion_status,
                "steps_json": payload,
            }
        )
    return rows


def score_predictions(predictions: list[dict[str, str]], root: Path | None = None) -> ScoreReport:
    base = root or dataset_dir()
    with (base / "sample_output.csv").open(encoding="utf-8", newline="") as handle:
        expected = list(csv.DictReader(handle))
    return score_rows(expected, predictions)


def main() -> int:
    predictions = predict_sample()
    repeated = predict_sample()
    same = [row["steps_json"] for row in predictions] == [row["steps_json"] for row in repeated]
    same = same and [row["deletion_status"] for row in predictions] == [row["deletion_status"] for row in repeated]
    report = score_predictions(predictions)
    print(format_report(report))
    print(f"repeatable={same}")
    print(explain_predictions(predictions))
    mismatches = []
    base = dataset_dir()
    with (base / "sample_output.csv").open(encoding="utf-8", newline="") as handle:
        expected = {row["case_id"]: row for row in csv.DictReader(handle)}
    for row in predictions:
        wanted = expected[row["case_id"]]
        if row["deletion_status"] != wanted["deletion_status"] or steps_from_json(row["steps_json"]) != steps_from_json(
            wanted["steps_json"]
        ):
            mismatches.append(row["case_id"])
    print("mismatch_cases=" + ",".join(mismatches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
