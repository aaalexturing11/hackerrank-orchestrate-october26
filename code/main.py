"""Audit every deletion request and write repository-root output.csv.

Uses the same DeletionAuditor path as the public-sample evaluator.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from code.config import dataset_dir, repo_root
from code.engine.auditor import DeletionAuditor
from code.engine.step_builder import validate_case
from code.identity.resolver import IdentityResolver
from code.ingestion.csv_loader import load_dataset
from code.ingestion.evidence_registry import EvidenceRegistry


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    dataset = load_dataset()
    registry = EvidenceRegistry(dataset, dataset_dir())
    results = registry.parse_all()
    observations = [item for result in results for item in result.observations]
    auditor = DeletionAuditor(IdentityResolver.from_dataset(dataset), observations, dataset.activities)
    known = {item.file_id for item in dataset.evidence}
    known.update(item.activity_id for item in dataset.activities)
    known.update(item.audit_id for item in dataset.audit_log)
    evidence_times = {item.file_id: item.captured_at for item in dataset.evidence}
    rows: list[dict[str, str]] = []
    violations = 0
    for request in sorted(dataset.requests, key=lambda item: item.case_id):
        decision = auditor.audit(request)
        issues = validate_case(
            deletion_status=decision.deletion_status,
            steps=decision.steps,
            known_evidence_ids=known,
            evidence_times=evidence_times,
            audit_at=request.audit_at,
        )
        if issues:
            violations += 1
            logging.error("%s invalid steps: %s", request.case_id, issues)
        rows.append(
            {
                "case_id": decision.case_id,
                "deletion_status": decision.deletion_status,
                "steps_json": json.dumps([step.as_dict() for step in decision.steps], separators=(",", ":")),
            }
        )
    destination = repo_root() / "output.csv"
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["case_id", "deletion_status", "steps_json"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter(row["deletion_status"] for row in rows)
    print(f"requests={len(rows)}")
    print(f"parse_failures={sum(1 for result in results if result.status == 'failed')}")
    print(f"status_COMPLETE={counts['COMPLETE']}")
    print(f"status_INCOMPLETE={counts['INCOMPLETE']}")
    print(f"status_NOT_APPLICABLE={counts['NOT_APPLICABLE']}")
    print(f"contract_violations={violations}")
    print(f"output_csv={destination}")
    return 1 if violations or len(rows) != len(dataset.requests) else 0


if __name__ == "__main__":
    raise SystemExit(main())
