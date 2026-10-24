"""Load participant CSVs without changing source files or identifier strings."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from code.config import dataset_dir
from code.models import (
    ActivityRecord,
    DeletionRequest,
    EvidenceFile,
    IdentityChange,
    IdentitySnapshot,
    PolicyRule,
)

REQUEST_COLUMNS = (
    "case_id",
    "email",
    "requested_at",
    "reported_status",
    "reported_at",
    "audit_at",
    "request_text",
)
IDENTITY_COLUMNS = ("user_id", "name", "email", "phone", "email_hash", "updated_at")
AUDIT_COLUMNS = ("audit_id", "user_id", "event_time", "field_name", "old_value", "new_value")
ACTIVITY_COLUMNS = (
    "activity_id",
    "event_time",
    "event_type",
    "source_system",
    "target_system",
    "resource_id",
    "reported_result",
    "details",
)
RULE_COLUMNS = ("rule_id", "data_category", "condition", "required_action")
EVIDENCE_COLUMNS = ("file_id", "file_path", "origin", "captured_at")

REPORTED_STATUSES = frozenset({"COMPLETE", "PARTIALLY_COMPLETE", "NOT_STARTED"})
RULE_ACTIONS = frozenset({"DELETE", "REDACT", "ANONYMIZE", "RETAIN"})


def parse_utc(value: str, *, source: str) -> datetime:
    text = value.strip()
    if not text.endswith("Z"):
        raise ValueError(f"{source}: timestamp {value!r} is not UTC Zulu form")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValueError(f"{source}: unparseable timestamp {value!r}") from exc
    return parsed.replace(tzinfo=timezone.utc)


def _require_columns(fieldnames: list[str] | None, required: tuple[str, ...], filename: str) -> None:
    found = list(fieldnames or [])
    missing = [name for name in required if name not in found]
    if missing:
        raise ValueError(f"{filename} missing columns: {', '.join(missing)}")


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        _names = list(reader.fieldnames or [])
        rows = []
        for row in reader:
            # DictReader already returns strings. Do not coerce identifiers.
            rows.append({key: (value if value is not None else "") for key, value in row.items()})
        return _names, rows


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for value in values:
        if value in seen and value not in dupes:
            dupes.append(value)
        seen.add(value)
    return dupes


@dataclass
class Dataset:
    requests: list[DeletionRequest]
    identities: list[IdentitySnapshot]
    audit_log: list[IdentityChange]
    activities: list[ActivityRecord]
    rules: list[PolicyRule]
    evidence: list[EvidenceFile]
    warnings: list[str] = field(default_factory=list)
    duplicate_ids: dict[str, list[str]] = field(default_factory=dict)

    requests_by_id: dict[str, DeletionRequest] = field(default_factory=dict)
    identities_by_user: dict[str, IdentitySnapshot] = field(default_factory=dict)
    audit_by_user: dict[str, list[IdentityChange]] = field(default_factory=dict)
    activities_by_id: dict[str, ActivityRecord] = field(default_factory=dict)
    activities_by_resource: dict[str, list[ActivityRecord]] = field(default_factory=dict)
    evidence_by_id: dict[str, EvidenceFile] = field(default_factory=dict)
    rules_by_category: dict[str, list[PolicyRule]] = field(default_factory=dict)

    def index(self) -> None:
        self.requests_by_id = {row.case_id: row for row in self.requests}
        self.identities_by_user = {row.user_id: row for row in self.identities}
        audit_by_user: dict[str, list[IdentityChange]] = defaultdict(list)
        for row in self.audit_log:
            audit_by_user[row.user_id].append(row)
        for rows in audit_by_user.values():
            rows.sort(key=lambda item: item.event_time)
        self.audit_by_user = dict(audit_by_user)
        self.activities_by_id = {row.activity_id: row for row in self.activities}
        by_resource: dict[str, list[ActivityRecord]] = defaultdict(list)
        for row in self.activities:
            by_resource[row.resource_id].append(row)
        self.activities_by_resource = dict(by_resource)
        self.evidence_by_id = {row.file_id: row for row in self.evidence}
        by_category: dict[str, list[PolicyRule]] = defaultdict(list)
        for row in self.rules:
            by_category[row.data_category].append(row)
        self.rules_by_category = dict(by_category)


def load_dataset(root: Path | None = None) -> Dataset:
    base = root if root is not None else dataset_dir()
    warnings: list[str] = []
    duplicate_ids: dict[str, list[str]] = {}

    request_names, request_rows = _read_rows(base / "deletion_requests.csv")
    _require_columns(request_names, REQUEST_COLUMNS, "deletion_requests.csv")
    requests = [
        DeletionRequest(
            case_id=row["case_id"],
            email=row["email"],
            requested_at=parse_utc(row["requested_at"], source=f"{row['case_id']}.requested_at"),
            reported_status=row["reported_status"],
            reported_at=parse_utc(row["reported_at"], source=f"{row['case_id']}.reported_at"),
            audit_at=parse_utc(row["audit_at"], source=f"{row['case_id']}.audit_at"),
            request_text=row["request_text"],
        )
        for row in request_rows
    ]
    for request in requests:
        if request.reported_status not in REPORTED_STATUSES:
            warnings.append(f"{request.case_id} has unexpected reported_status {request.reported_status}")
        if not (request.requested_at <= request.reported_at <= request.audit_at):
            warnings.append(f"{request.case_id} timestamps are not requested <= reported <= audit")

    identity_names, identity_rows = _read_rows(base / "user_identities.csv")
    _require_columns(identity_names, IDENTITY_COLUMNS, "user_identities.csv")
    identities = [
        IdentitySnapshot(
            user_id=row["user_id"],
            name=row["name"],
            email=row["email"],
            phone=row["phone"],
            email_hash=row["email_hash"],
            updated_at=parse_utc(row["updated_at"], source=f"{row['user_id']}.updated_at"),
        )
        for row in identity_rows
    ]

    audit_names, audit_rows = _read_rows(base / "user_audit_log.csv")
    _require_columns(audit_names, AUDIT_COLUMNS, "user_audit_log.csv")
    audit_log = [
        IdentityChange(
            audit_id=row["audit_id"],
            user_id=row["user_id"],
            event_time=parse_utc(row["event_time"], source=f"{row['audit_id']}.event_time"),
            field_name=row["field_name"],
            old_value=row["old_value"],
            new_value=row["new_value"],
        )
        for row in audit_rows
    ]

    activity_names, activity_rows = _read_rows(base / "system_activity.csv")
    _require_columns(activity_names, ACTIVITY_COLUMNS, "system_activity.csv")
    activities = [
        ActivityRecord(
            activity_id=row["activity_id"],
            event_time=parse_utc(row["event_time"], source=f"{row['activity_id']}.event_time"),
            event_type=row["event_type"],
            source_system=row["source_system"],
            target_system=row["target_system"],
            resource_id=row["resource_id"],
            reported_result=row["reported_result"],
            details=row["details"],
        )
        for row in activity_rows
    ]

    rule_names, rule_rows = _read_rows(base / "deletion_rules.csv")
    _require_columns(rule_names, RULE_COLUMNS, "deletion_rules.csv")
    rules = [
        PolicyRule(
            rule_id=row["rule_id"],
            data_category=row["data_category"],
            condition=row["condition"],
            required_action=row["required_action"],
        )
        for row in rule_rows
    ]
    for rule in rules:
        if rule.required_action not in RULE_ACTIONS:
            warnings.append(f"{rule.rule_id} has unexpected action {rule.required_action}")

    evidence_names, evidence_rows = _read_rows(base / "evidence_files.csv")
    _require_columns(evidence_names, EVIDENCE_COLUMNS, "evidence_files.csv")
    evidence = [
        EvidenceFile(
            file_id=row["file_id"],
            file_path=row["file_path"],
            origin=row["origin"],
            captured_at=parse_utc(row["captured_at"], source=f"{row['file_id']}.captured_at"),
        )
        for row in evidence_rows
    ]
    for item in evidence:
        if not (base / item.file_path).is_file():
            warnings.append(f"{item.file_id} path is missing: {item.file_path}")

    for label, values in (
        ("case_id", [row.case_id for row in requests]),
        ("user_id", [row.user_id for row in identities]),
        ("audit_id", [row.audit_id for row in audit_log]),
        ("activity_id", [row.activity_id for row in activities]),
        ("rule_id", [row.rule_id for row in rules]),
        ("file_id", [row.file_id for row in evidence]),
    ):
        found = _duplicates(values)
        if found:
            duplicate_ids[label] = found
            warnings.append(f"duplicate {label}: {', '.join(found[:10])}")

    dataset = Dataset(
        requests=requests,
        identities=identities,
        audit_log=audit_log,
        activities=activities,
        rules=rules,
        evidence=evidence,
        warnings=warnings,
        duplicate_ids=duplicate_ids,
    )
    dataset.index()
    return dataset
