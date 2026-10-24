"""Explain public-sample steps the auditor did not emit.

This module reads sample_output.csv only after predictions exist. The planner
does not import it.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from code.config import dataset_dir
from code.engine.step_builder import steps_from_json
from code.identity.resolver import IdentityResolver
from code.ingestion.csv_loader import load_dataset, parse_utc
from code.ingestion.evidence_registry import EvidenceRegistry
from code.models import ActivityRecord, DeletionRequest, Observation

CLASS_LABELS = {
    "A": "Parser omission",
    "B": "Identity-resolution omission",
    "C": "Temporal-state reconstruction omission",
    "D": "Resource-association omission",
    "E": "Policy or verification-coverage omission",
    "F": "Unverifiable from participant-facing evidence",
}

_ACTION_FOR_OPERATION = {
    "VERIFY_RECORD_ABSENT": "DELETE",
    "DELETE_RECORD": "DELETE",
    "REPORT_REMAINING_RECORD": "DELETE",
    "VERIFY_RECORD_PRESENT": "RETAIN",
    "VERIFY_RECORD_REDACTED": "REDACT",
    "REDACT_RECORD": "REDACT",
    "REPORT_EXPOSED_PII": "REDACT",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZE",
    "ANONYMIZE_RECORD": "ANONYMIZE",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLE",
    "DISABLE_DATA_FLOW": "DISABLE",
    "VERIFY_RESTORE_BLOCKED": "RETAIN",
    "BLOCK_RESTORE": "RETAIN",
}


def explain_predictions(predictions: list[dict[str, str]], root: Path | None = None) -> str:
    base = root or dataset_dir()
    dataset = load_dataset(base)
    observations = [
        item for result in EvidenceRegistry(dataset, base).parse_all() for item in result.observations
    ]
    resolver = IdentityResolver.from_dataset(dataset)
    file_bytes = {
        item.file_id: (base / item.file_path).read_bytes()
        for item in dataset.evidence
        if (base / item.file_path).is_file()
    }
    with (base / "sample_output.csv").open(encoding="utf-8", newline="") as handle:
        import csv

        expected = {row["case_id"]: row for row in csv.DictReader(handle)}
    with (base / "sample_deletion_requests.csv").open(encoding="utf-8", newline="") as handle:
        import csv

        requests = {
            row["case_id"]: DeletionRequest(
                case_id=row["case_id"],
                email=row["email"],
                requested_at=parse_utc(row["requested_at"], source="requested_at"),
                reported_status=row["reported_status"],
                reported_at=parse_utc(row["reported_at"], source="reported_at"),
                audit_at=parse_utc(row["audit_at"], source="audit_at"),
                request_text=row["request_text"],
            )
            for row in csv.DictReader(handle)
        }
    predicted = {row["case_id"]: row for row in predictions}
    lines: list[str] = []
    classes: Counter[str] = Counter()
    for case_id in sorted(expected, key=lambda item: (len(item), item)):
        request = requests[case_id]
        want = steps_from_json(expected[case_id]["steps_json"])
        got = steps_from_json(predicted[case_id]["steps_json"])
        got_keys = Counter(step.comparable() for step in got)
        resolved = resolver.resolve_email(request.email, audit_at=request.audit_at)
        aliases = (
            resolver.aliases_at(resolved.user_id, request.audit_at)
            if resolved.status == "unique" and resolved.user_id
            else None
        )
        for step in want:
            key = step.comparable()
            if got_keys[key]:
                got_keys[key] -= 1
                continue
            label, reason, established = _classify(
                step=step,
                request=request,
                aliases=aliases,
                observations=observations,
                activities=dataset.activities,
                file_bytes=file_bytes,
            )
            classes[label] += 1
            lines.extend(
                _render(
                    case_id=case_id,
                    step=step,
                    label=label,
                    reason=reason,
                    established=established,
                    aliases=aliases,
                    observations=observations,
                    activities=dataset.activities,
                    rules=dataset.rules,
                    request=request,
                )
            )
    header = ["missing_step_classes:"]
    for label in "ABCDEF":
        header.append(f"  {label} {CLASS_LABELS[label]}={classes[label]}")
    header.append(f"missing_steps={sum(classes.values())}")
    return "\n".join(header + [""] + lines)


def resource_in_payload(resource_id: str, payload: bytes) -> bool:
    """Match a resource id without treating it as a prefix of a longer id."""
    needle = re.compile(rb"(?<![A-Za-z0-9_])" + re.escape(resource_id.encode("utf-8")) + rb"(?![A-Za-z0-9_])")
    return needle.search(payload) is not None


def _classify(step, request, aliases, observations, activities, file_bytes) -> tuple[str, str, bool]:
    resource_id = step.resource_id
    files_with_id = sorted(
        file_id for file_id, payload in file_bytes.items() if resource_in_payload(resource_id, payload)
    )
    related = [row for row in observations if row.resource_id == resource_id]
    eligible = [row for row in related if row.eligible_at(request.audit_at) and not row.is_claim]
    late = [row for row in related if row.captured_at is not None and row.captured_at > request.audit_at]
    matched = [row for row in eligible if aliases is not None and aliases.intersects(row.identifiers)]
    acts = [row for row in activities if row.resource_id == resource_id and row.event_time <= request.audit_at]
    subject_named = _activity_names_subject(acts, aliases)
    established = bool(matched or subject_named)
    cited = step.evidence_id
    if matched:
        return (
            "E",
            "an eligible observation already carries this subject's identifier, and the planner still emitted no step",
            True,
        )
    if cited and cited not in files_with_id:
        if late and not eligible:
            return (
                "C",
                f"{cited} does not contain {resource_id}; the only observations are captured after audit_at",
                False,
            )
        return (
            "F",
            f"cited file {cited or '(empty)'} does not contain {resource_id}",
            False,
        )
    if late and not eligible:
        return ("C", "the only observations of this resource are captured after audit_at", False)
    if eligible and all(row.identifiers.is_empty() for row in eligible) and not subject_named:
        return (
            "B",
            "an eligible observation exists and its identity fields are empty; no activity names this subject",
            False,
        )
    if eligible and not matched and not subject_named:
        return (
            "B",
            "eligible observations carry identifiers for a different subject",
            False,
        )
    if not related and files_with_id:
        return (
            "A",
            "the resource id occurs in " + ",".join(files_with_id) + " and no observation was emitted",
            False,
        )
    if acts and not subject_named:
        return (
            "D",
            "an activity names the resource and does not name this subject",
            False,
        )
    return (
        "F",
        "no participant-facing file or activity establishes this resource for this subject",
        False,
    )


def _activity_names_subject(activities: list[ActivityRecord], aliases) -> bool:
    if aliases is None:
        return False
    for activity in activities:
        text = activity.details.casefold()
        if aliases.user_id.casefold() in text:
            return True
        if any(email in text for email in aliases.emails):
            return True
    return False


def _render(case_id, step, label, reason, established, aliases, observations, activities, rules, request) -> list[str]:
    related = [row for row in observations if row.resource_id == step.resource_id]
    acts = [row for row in activities if row.resource_id == step.resource_id and row.event_time <= request.audit_at]
    action = _ACTION_FOR_OPERATION.get(step.operation, "")
    applicable = [rule.rule_id for rule in rules if rule.required_action == action]
    alias_text = "unresolved"
    if aliases is not None:
        alias_text = f"user_id={aliases.user_id} emails={','.join(sorted(aliases.emails)) or '-'}"
    obs_text = "-"
    if related:
        obs_text = "; ".join(
            f"{row.evidence_id} presence={row.presence} eligible={row.eligible_at(request.audit_at)} "
            f"ids_empty={row.identifiers.is_empty()} captured={row.captured_at}"
            for row in related[:6]
        )
    act_text = "-"
    if acts:
        act_text = "; ".join(
            f"{row.activity_id} {row.event_time.isoformat()} {row.event_type} {row.reported_result}"
            for row in acts[:4]
        )
    return [
        f"{case_id} class={label} {CLASS_LABELS[label]}",
        f"  expected {step.phase} {step.operation} {step.state} {step.system_id} {step.resource_id} evidence={step.evidence_id or '(empty)'}",
        f"  aliases {alias_text}",
        f"  observations {obs_text}",
        f"  activities {act_text}",
        f"  rules {','.join(applicable) or '-'}",
        f"  omitted_because {reason}",
        f"  independently_established {established}",
    ]


def main() -> int:
    from code.evaluation.predict import predict_sample

    print(explain_predictions(predict_sample()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
