"""Canonical step ordering and contract validation.

This module does not decide which steps a case needs. It checks and orders
steps the next phase will produce.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from code.config import RESOURCE_SORT
from code.models import AuditStep, ValidationIssue
from code.policy.rules import ALLOWED_PAIRS, OPERATION_ORDER, PHASES

OUTPUT_HEADER = ("case_id", "deletion_status", "steps_json")
STATUSES = frozenset({"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"})
_RESOURCE_NUMBER = re.compile(r"_(\d+)$")


def finding(
    *,
    system_id: str,
    resource_id: str,
    operation: str,
    evidence_id: str,
    step_no: int = 0,
) -> AuditStep:
    state = _require_pair("FINDING", operation)
    if not evidence_id:
        raise ValueError("findings require evidence_id")
    return AuditStep(step_no, "FINDING", system_id, resource_id, operation, state, evidence_id)


def remediation(
    *,
    system_id: str,
    resource_id: str,
    operation: str,
    step_no: int = 0,
) -> AuditStep:
    state = _require_pair("REMEDIATION", operation)
    return AuditStep(step_no, "REMEDIATION", system_id, resource_id, operation, state, "")


def verification(
    *,
    system_id: str,
    resource_id: str,
    operation: str,
    evidence_id: str,
    step_no: int = 0,
) -> AuditStep:
    state = _require_pair("VERIFICATION", operation)
    return AuditStep(step_no, "VERIFICATION", system_id, resource_id, operation, state, evidence_id)


def _require_pair(phase: str, operation: str) -> str:
    state = ALLOWED_PAIRS.get((phase, operation))
    if state is None:
        raise ValueError(f"{phase}/{operation} is not an allowed operation")
    return state


def resource_sort_key(resource_id: str, mode: str | None = None) -> tuple:
    selected = mode or RESOURCE_SORT
    if selected == "numeric":
        match = _RESOURCE_NUMBER.search(resource_id)
        number = int(match.group(1)) if match else -1
        return (resource_id[: match.start()] if match else resource_id, number, resource_id)
    if selected != "lexicographic":
        raise ValueError(f"unknown resource sort mode {selected}")
    return (resource_id,)


def sort_steps(steps: list[AuditStep], *, resource_sort: str | None = None) -> list[AuditStep]:
    phase_index = {phase: index for index, phase in enumerate(PHASES)}
    operation_index = {operation: index for index, operation in enumerate(OPERATION_ORDER)}

    def key(step: AuditStep) -> tuple:
        return (
            phase_index[step.phase],
            operation_index[step.operation],
            step.system_id,
            resource_sort_key(step.resource_id, resource_sort),
        )

    ordered = sorted(steps, key=key)
    return [
        AuditStep(
            index,
            step.phase,
            step.system_id,
            step.resource_id,
            step.operation,
            step.state,
            step.evidence_id,
        )
        for index, step in enumerate(ordered, start=1)
    ]


def steps_from_json(payload: str) -> list[AuditStep]:
    raw = json.loads(payload)
    if not isinstance(raw, list):
        raise ValueError("steps_json must be an array")
    steps: list[AuditStep] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("step must be an object")
        steps.append(
            AuditStep(
                step_no=int(item["step_no"]),
                phase=str(item["phase"]),
                system_id=str(item["system_id"]),
                resource_id=str(item["resource_id"]),
                operation=str(item["operation"]),
                state=str(item["state"]),
                evidence_id=str(item["evidence_id"]),
            )
        )
    return steps


def validate_header(fieldnames: list[str] | None) -> list[ValidationIssue]:
    if tuple(fieldnames or []) != OUTPUT_HEADER:
        return [ValidationIssue("bad_header", f"header must be {','.join(OUTPUT_HEADER)}")]
    return []


def validate_case(
    *,
    deletion_status: str,
    steps: list[AuditStep],
    known_evidence_ids: set[str] | None = None,
    evidence_times: dict[str, datetime] | None = None,
    audit_at: datetime | None = None,
    resource_sort: str | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if deletion_status not in STATUSES:
        issues.append(ValidationIssue("bad_status", f"unknown deletion_status {deletion_status}"))
        return issues
    if deletion_status == "NOT_APPLICABLE":
        if steps:
            issues.append(ValidationIssue("not_applicable_nonempty", "NOT_APPLICABLE requires an empty array"))
        return issues
    expected_order = sort_steps(steps, resource_sort=resource_sort)
    for index, step in enumerate(steps, start=1):
        if step.step_no != index:
            issues.append(ValidationIssue("numbering", f"step_no {step.step_no} is not {index}", step.step_no))
        if step.phase not in PHASES:
            issues.append(ValidationIssue("bad_phase", f"illegal phase {step.phase}", step.step_no))
            continue
        expected_state = ALLOWED_PAIRS.get((step.phase, step.operation))
        if expected_state is None or step.state != expected_state:
            issues.append(
                ValidationIssue(
                    "bad_pair",
                    f"{step.phase}/{step.operation}/{step.state} is not an allowed triple",
                    step.step_no,
                )
            )
        if deletion_status == "COMPLETE" and step.phase != "VERIFICATION":
            issues.append(ValidationIssue("complete_non_verification", "COMPLETE allows only VERIFICATION", step.step_no))
        _check_evidence(
            issues,
            deletion_status,
            step,
            known_evidence_ids=known_evidence_ids,
            evidence_times=evidence_times,
            audit_at=audit_at,
        )
    comparable = [step.comparable() for step in steps]
    expected_comparable = [step.comparable() for step in expected_order]
    if comparable != expected_comparable:
        issues.append(ValidationIssue("order", "steps are not in contract order"))
    return issues


def _check_evidence(
    issues: list[ValidationIssue],
    deletion_status: str,
    step: AuditStep,
    *,
    known_evidence_ids: set[str] | None,
    evidence_times: dict[str, datetime] | None,
    audit_at: datetime | None,
) -> None:
    if step.phase == "FINDING" or (deletion_status == "COMPLETE" and step.phase == "VERIFICATION"):
        if step.evidence_id == "":
            issues.append(ValidationIssue("evidence_empty", "this step requires evidence_id", step.step_no))
            return
        if known_evidence_ids is not None and step.evidence_id not in known_evidence_ids:
            issues.append(ValidationIssue("evidence_unknown", f"unknown evidence_id {step.evidence_id}", step.step_no))
        if evidence_times is not None and audit_at is not None and step.evidence_id in evidence_times:
            if evidence_times[step.evidence_id] > audit_at:
                issues.append(ValidationIssue("evidence_after_audit", "evidence captured after audit_at", step.step_no))
        return
    if step.evidence_id != "":
        issues.append(
            ValidationIssue(
                "evidence_present",
                "remediation and future verification require an empty evidence_id",
                step.step_no,
            )
        )
