"""Compare predicted deletion-audit rows with expected rows."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

from code.engine.step_builder import steps_from_json
from code.models import AuditStep


@dataclass
class FieldMismatch:
    case_id: str
    step_no: int
    field: str
    expected: str
    actual: str


@dataclass
class CaseFailure:
    case_id: str
    category: str
    message: str


@dataclass
class ScoreReport:
    cases: int
    status_correct: int
    exact_rows: int
    field_matches: int
    field_total: int
    sequence_exact: int
    operation_overlap: int = 0
    operation_expected: int = 0
    operation_predicted: int = 0
    failures: list[CaseFailure] = field(default_factory=list)
    field_mismatches: list[FieldMismatch] = field(default_factory=list)

    @property
    def status_accuracy(self) -> float:
        return _ratio(self.status_correct, self.cases)

    @property
    def row_accuracy(self) -> float:
        return _ratio(self.exact_rows, self.cases)

    @property
    def field_accuracy(self) -> float:
        return _ratio(self.field_matches, self.field_total)

    @property
    def sequence_accuracy(self) -> float:
        return _ratio(self.sequence_exact, self.cases)

    @property
    def operation_precision(self) -> float:
        return _ratio(self.operation_overlap, self.operation_predicted)

    @property
    def operation_recall(self) -> float:
        return _ratio(self.operation_overlap, self.operation_expected)

    def grouped(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for failure in self.failures:
            counts[failure.category] = counts.get(failure.category, 0) + 1
        for mismatch in self.field_mismatches:
            key = f"field:{mismatch.field}"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def score_rows(expected: list[dict[str, str]], predicted: list[dict[str, str]]) -> ScoreReport:
    expected_by_id = {row["case_id"]: row for row in expected}
    predicted_by_id = {row["case_id"]: row for row in predicted}
    report = ScoreReport(cases=len(expected_by_id), status_correct=0, exact_rows=0, field_matches=0, field_total=0, sequence_exact=0)
    for case_id in sorted(set(expected_by_id) - set(predicted_by_id)):
        report.failures.append(CaseFailure(case_id, "missing_case", "prediction is missing"))
    for case_id in sorted(set(predicted_by_id) - set(expected_by_id)):
        report.failures.append(CaseFailure(case_id, "extra_case", "prediction has an unexpected case"))
    for case_id in sorted(expected_by_id.keys() & predicted_by_id.keys()):
        _score_case(report, case_id, expected_by_id[case_id], predicted_by_id[case_id])
    return report


def _score_case(report: ScoreReport, case_id: str, expected: dict[str, str], predicted: dict[str, str]) -> None:
    status_ok = expected["deletion_status"] == predicted["deletion_status"]
    if status_ok:
        report.status_correct += 1
    else:
        report.failures.append(
            CaseFailure(
                case_id,
                "status",
                f"{predicted['deletion_status']} != {expected['deletion_status']}",
            )
        )
    try:
        expected_steps = steps_from_json(expected["steps_json"])
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        report.failures.append(CaseFailure(case_id, "json_parse", f"expected steps_json: {exc}"))
        return
    try:
        predicted_steps = steps_from_json(predicted["steps_json"])
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        report.failures.append(CaseFailure(case_id, "json_parse", f"predicted steps_json: {exc}"))
        return
    if [step.step_no for step in predicted_steps] != list(range(1, len(predicted_steps) + 1)):
        report.failures.append(CaseFailure(case_id, "numbering", "step_no is not consecutive from 1"))
    expected_seq = [step.comparable() for step in expected_steps]
    predicted_seq = [step.comparable() for step in predicted_steps]
    expected_counts = Counter(expected_seq)
    predicted_counts = Counter(predicted_seq)
    report.operation_overlap += sum((expected_counts & predicted_counts).values())
    report.operation_expected += len(expected_steps)
    report.operation_predicted += len(predicted_steps)
    if expected_seq == predicted_seq:
        report.sequence_exact += 1
    else:
        report.failures.append(CaseFailure(case_id, "sequence", "step sequence differs"))
        if sorted(expected_seq) == sorted(predicted_seq):
            report.failures.append(CaseFailure(case_id, "reorder", "the same steps are in a different order"))
        if len(predicted_steps) < len(expected_steps):
            report.failures.append(CaseFailure(case_id, "missing_step", f"missing {len(expected_steps) - len(predicted_steps)} step(s)"))
        elif len(predicted_steps) > len(expected_steps):
            report.failures.append(CaseFailure(case_id, "extra_step", f"extra {len(predicted_steps) - len(expected_steps)} step(s)"))
    _score_fields(report, case_id, expected_steps, predicted_steps)
    if status_ok and expected_seq == predicted_seq:
        report.exact_rows += 1


def _score_fields(
    report: ScoreReport,
    case_id: str,
    expected_steps: list[AuditStep],
    predicted_steps: list[AuditStep],
) -> None:
    compared = max(len(expected_steps), len(predicted_steps))
    fields = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")
    for index in range(compared):
        report.field_total += len(fields)
        if index >= len(expected_steps) or index >= len(predicted_steps):
            continue
        expected = expected_steps[index]
        predicted = predicted_steps[index]
        for name in fields:
            if getattr(expected, name) == getattr(predicted, name):
                report.field_matches += 1
            else:
                report.field_mismatches.append(
                    FieldMismatch(
                        case_id=case_id,
                        step_no=index + 1,
                        field=name,
                        expected=str(getattr(expected, name)),
                        actual=str(getattr(predicted, name)),
                    )
                )


def format_report(report: ScoreReport) -> str:
    lines = [
        f"cases={report.cases}",
        f"status_accuracy={report.status_accuracy:.4f} ({report.status_correct}/{report.cases})",
        f"row_accuracy={report.row_accuracy:.4f} ({report.exact_rows}/{report.cases})",
        f"field_accuracy={report.field_accuracy:.4f} ({report.field_matches}/{report.field_total})",
        f"sequence_accuracy={report.sequence_accuracy:.4f} ({report.sequence_exact}/{report.cases})",
        f"operation_precision={report.operation_precision:.4f} ({report.operation_overlap}/{report.operation_predicted})",
        f"operation_recall={report.operation_recall:.4f} ({report.operation_overlap}/{report.operation_expected})",
        f"missing_operations={report.operation_expected - report.operation_overlap}",
        f"extra_operations={report.operation_predicted - report.operation_overlap}",
        f"failures={len(report.failures)} field_mismatches={len(report.field_mismatches)}",
    ]
    grouped = report.grouped()
    if grouped:
        lines.append("groups:")
        for name, count in grouped.items():
            lines.append(f"  {name}={count}")
    return "\n".join(lines)
