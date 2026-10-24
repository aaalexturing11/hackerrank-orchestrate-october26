"""Process every evaluation request in memory.

This does not write output.csv and does not read sample_output.csv.
"""

from __future__ import annotations

import time
from collections import Counter

from code.config import dataset_dir
from code.engine.auditor import DeletionAuditor
from code.engine.step_builder import validate_case
from code.evaluation.usage import UsageLedger
from code.identity.resolver import IdentityResolver
from code.ingestion.csv_loader import load_dataset
from code.ingestion.evidence_registry import EvidenceRegistry
from code.ingestion.image_facts import IMAGE_FACTS


def main() -> int:
    started = time.perf_counter()
    base = dataset_dir()
    dataset = load_dataset(base)
    results = EvidenceRegistry(dataset, base).parse_all()
    observations = [item for result in results for item in result.observations]
    auditor = DeletionAuditor(IdentityResolver.from_dataset(dataset), observations, dataset.activities)
    known = {item.file_id for item in dataset.evidence}
    known.update(item.activity_id for item in dataset.activities)
    known.update(item.audit_id for item in dataset.audit_log)
    evidence_times = {item.file_id: item.captured_at for item in dataset.evidence}
    statuses: Counter[str] = Counter()
    phases: Counter[str] = Counter()
    operations: Counter[str] = Counter()
    unresolved = 0
    ambiguous = 0
    invalid_cases = 0
    invalid_evidence = 0
    step_count = 0
    for request in dataset.requests:
        decision = auditor.audit(request)
        statuses[decision.deletion_status] += 1
        note_text = " ".join(decision.notes)
        if "ambiguous" in note_text:
            ambiguous += 1
        if "unresolved" in note_text:
            unresolved += 1
        issues = validate_case(
            deletion_status=decision.deletion_status,
            steps=decision.steps,
            known_evidence_ids=known,
            evidence_times=evidence_times,
            audit_at=request.audit_at,
        )
        if issues:
            invalid_cases += 1
        for step in decision.steps:
            step_count += 1
            phases[step.phase] += 1
            operations[step.operation] += 1
            if step.evidence_id and step.evidence_id not in known:
                invalid_evidence += 1
    elapsed = time.perf_counter() - started
    usage = UsageLedger().summary()
    print(f"cases_processed={len(dataset.requests)}")
    print(f"parse_failures={sum(1 for result in results if result.status == 'failed')}")
    print(f"image_fact_files={len(IMAGE_FACTS)}")
    for status in ("COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"):
        print(f"status_{status}={statuses[status]}")
    print(f"identity_unresolved={unresolved}")
    print(f"identity_ambiguous={ambiguous}")
    print(f"steps={step_count}")
    for phase in ("FINDING", "REMEDIATION", "VERIFICATION"):
        print(f"phase_{phase}={phases[phase]}")
    for operation, count in sorted(operations.items()):
        print(f"operation_{operation}={count}")
    print(f"contract_violations={invalid_cases}")
    print(f"invalid_evidence_references={invalid_evidence}")
    print(f"model_calls={usage['model_calls']}")
    print(f"input_tokens={usage['input_tokens']}")
    print(f"output_tokens={usage['output_tokens']}")
    print(f"estimated_cost={usage['estimated_cost']}")
    print(f"duration_seconds={elapsed:.2f}")
    print("output_csv_written=false")
    return 1 if invalid_cases or invalid_evidence else 0


if __name__ == "__main__":
    raise SystemExit(main())
