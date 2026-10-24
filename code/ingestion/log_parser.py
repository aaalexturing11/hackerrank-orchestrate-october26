"""Extract state-bearing log events.

Completion flags and HTTP 200 are not deletion proof. HTTP 404 and rows=0 on a
named lookup are explicit absence at that event time. Service-cache misses are
ignored; they are not customer CACHE_ENTRY records.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from code.ingestion.normalize import (
    as_bool,
    as_int,
    as_text,
    bag_from_mapping,
    direct_identifiers_present,
    make_observation,
    parse_time,
)
from code.models import EvidenceFile, Observation, ParseResult

TOKEN_RE = re.compile(r"""([A-Za-z_][\w-]*)=("(?:\\.|[^"\\])*"|[^\s]+)""")
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
BRACKET_RE = re.compile(
    r"\[(?:DEBUG|INFO|WARN|ERROR)\] \[([^\]]+)\] \[([^\]]+)\] ([A-Za-z0-9_]+):"
)
PIPE_RE = re.compile(r"\|\s+\w+\s+\|\s+(\S+)\s+\|\s+(\S+)\s+\|\s+([A-Za-z0-9_]+)\s+\|")

SKIP_EVENTS = frozenset(
    {
        "export_started",
        "export_completed",
        "connection_acquired",
        "cache_lookup",
        "consumer_lag",
        "thumbnail_failed",
        "batch_started",
        "checkpoint_saved",
        "dependency_retry",
        "dependency_recovered",
        "flag_snapshot_loaded",
    }
)

EVENT_RECORD_TYPE = {
    "profile_lookup_completed": "USER_PROFILE",
    "index_query_completed": "SEARCH_INDEX_ENTRY",
    "contact_lookup_completed": "CONTACT_LOOKUP",
    "contact_query_completed": "SUPPORT_ATTACHMENT",
    "connector_config_read_completed": "DATA_FLOW",
    "connector_heartbeat": "DATA_FLOW",
    "restore_policy_read_completed": "BACKUP_ARCHIVE",
    "restore_candidate_evaluated": "BACKUP_ARCHIVE",
    "support_ticket_read_completed": "SUPPORT_MESSAGE",
    "audit_record_read_completed": "SECURITY_AUDIT_LOG",
    "analytics_profile_read": "ANALYTICS_PROFILE",
    "deletion_marker_check": "SUPPORT_ATTACHMENT",
    "message_pii_scan": "SUPPORT_MESSAGE",
    "message_read": "SUPPORT_MESSAGE",
    "export_download_check_completed": "USER_EXPORT",
    "record_lookup": None,
}


def parse_log_file(evidence: EvidenceFile, path: Path) -> ParseResult:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    parsed: list[tuple[int, dict[str, str], datetime | None]] = []
    for number, line in enumerate(lines, start=1):
        fields, observed_at = _parse_line(line)
        if not fields:
            continue
        parsed.append((number, fields, observed_at))
    _propagate_trace(parsed)
    observations: list[Observation] = []
    for number, fields, observed_at in parsed:
        observation = _to_observation(evidence, number, fields, observed_at)
        if observation is not None:
            observations.append(observation)
    if observations:
        return ParseResult(
            file_id=evidence.file_id,
            path=str(path),
            kind="log",
            status="parsed",
            observations=observations,
        )
    return ParseResult(
        file_id=evidence.file_id,
        path=str(path),
        kind="log",
        status="partial",
        observations=[],
        warnings=["no state-bearing log events recognized; the file is not proof of absence"],
    )


def _parse_line(line: str) -> tuple[dict[str, str], datetime | None]:
    stamp = TIMESTAMP_RE.search(line)
    observed_at = parse_time(stamp.group(0)) if stamp else None
    brace = line.find("{")
    if brace >= 0 and line.rstrip().endswith("}"):
        try:
            payload = json.loads(line[brace:])
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            fields = {str(key): "" if value is None else str(value) for key, value in payload.items()}
            return fields, observed_at
    fields = _tokens(line)
    message = fields.get("message", "")
    if "event=" in message or "resource_id=" in message:
        fields.update(_tokens(message))
    bracket = BRACKET_RE.search(line)
    if bracket:
        fields.setdefault("service", bracket.group(1))
        fields.setdefault("trace_id", bracket.group(2))
        fields.setdefault("event", bracket.group(3))
    pipe = PIPE_RE.search(line)
    if pipe:
        fields.setdefault("service", pipe.group(1))
        fields.setdefault("trace_id", pipe.group(2))
        fields.setdefault("event", pipe.group(3))
    if fields.get("function"):
        fields.setdefault("service", fields["function"])
    if fields.get("requestId"):
        fields.setdefault("trace_id", fields["requestId"])
    return fields, observed_at


def _tokens(text: str) -> dict[str, str]:
    return {key: _unquote(raw) for key, raw in TOKEN_RE.findall(text)}


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        return inner.replace(r"\"", '"').replace(r"\\", "\\")
    return raw


def _trace_value(value: str | None) -> bool:
    """A trace key is usable only when it names something other than an explicit null."""
    if value is None:
        return False
    return value.strip().strip('"').casefold() not in {"", "null", "none", "n/a"}


def _propagate_trace(parsed: list[tuple[int, dict[str, str], datetime | None]]) -> None:
    carry_keys = (
        "lookup_key",
        "subject_ref",
        "subject_reference",
        "subject_key",
        "match_key",
        "correlation_key",
        "owner_key",
    )
    remembered: dict[str, dict[str, str]] = {}
    for _number, fields, _observed in parsed:
        trace = fields.get("trace_id")
        if not trace:
            continue
        bucket = remembered.setdefault(trace, {})
        for key in carry_keys:
            value = fields.get(key)
            if _trace_value(value):
                bucket[key] = value
            elif key in fields and not _trace_value(value):
                fields.pop(key, None)
        for key, value in bucket.items():
            fields.setdefault(key, value)


def _to_observation(
    evidence: EvidenceFile,
    line_number: int,
    fields: dict[str, str],
    observed_at: datetime | None,
) -> Observation | None:
    event = fields.get("event", "")
    if not event or event in SKIP_EVENTS or event.endswith("_started"):
        return None
    resource_id = as_text(fields.get("resource_id"))
    if resource_id is None:
        return None
    if event not in EVENT_RECORD_TYPE and not event.endswith("_completed") and event != "record_lookup":
        return None
    presence, token = _presence(fields)
    if presence == "unknown":
        return None
    record_type = fields.get("record_type") or EVENT_RECORD_TYPE.get(event) or event
    system_id = fields.get("system") or fields.get("service") or "unspecified"
    if system_id in {"readback_collector", "log_router"}:
        system_id = fields.get("service") or system_id
    bag = bag_from_mapping(fields)
    exposed = direct_identifiers_present(bag, fields)
    flow_enabled = as_bool(fields.get("enabled"))
    restore_allowed = as_bool(fields.get("restore_allowed"))
    restore_blocked = None if restore_allowed is None else not restore_allowed
    if event == "restore_candidate_evaluated":
        eligible = as_bool(fields.get("eligible"))
        blocked = as_bool(fields.get("deletion_block"))
        if eligible is True and blocked is False:
            restore_blocked = False
            presence = "present"
        elif blocked is True:
            restore_blocked = True
    if event == "connector_heartbeat":
        flow_enabled = as_bool(fields.get("enabled"))
        presence = "present"
    anonymized = True if fields.get("result", "").upper() == "ANONYMIZED" else None
    redacted = True if fields.get("result", "").upper() == "REDACTED" else None
    if fields.get("result", "").upper() == "IDENTIFIABLE":
        exposed = True
    marker = as_bool(fields.get("marker_found"))
    limitation = "explicit log observation"
    if marker is False:
        limitation = "deletion marker was not found; the read still returned the record" if presence == "present" else limitation
    return make_observation(
        evidence_id=evidence.file_id,
        system_id=system_id,
        resource_id=resource_id,
        observed_at=observed_at or evidence.captured_at,
        captured_at=evidence.captured_at,
        record_type=record_type,
        replica_role="unspecified",
        replica_name=None,
        presence=presence,
        identifiers=bag,
        identifiers_exposed=exposed if presence == "present" else None,
        source_locator=f"{evidence.file_id}:line:{line_number}",
        limitations=limitation,
        confidence="high",
        result_token=token,
        anonymized=anonymized,
        redacted=redacted,
        flow_enabled=flow_enabled,
        restore_blocked=restore_blocked,
        retention_until=parse_time(fields.get("retention_until")),
    )


def _presence(fields: dict[str, str]) -> tuple[str, str | None]:
    rows = as_int(fields.get("rows"))
    status = as_int(fields.get("http_status"))
    result = (fields.get("result") or "").upper()
    archive_present = as_bool(fields.get("archive_present"))
    available = as_bool(fields.get("available"))
    if status == 404 or rows == 0 or result in {"NOT_FOUND", "MISS"} or archive_present is False or available is False:
        return "absent", result or ("HTTP_404" if status == 404 else "ROWS_0")
    if rows is not None and rows > 0:
        return "present", result or f"ROWS_{rows}"
    if result in {"HIT", "FOUND", "IDENTIFIABLE", "ANONYMIZED", "REDACTED", "ACTIVE"}:
        return "present", result
    if archive_present is True or as_bool(fields.get("enabled")) is not None:
        return "present", result or "READ_COMPLETED"
    if any(fields.get(key) for key in ("requester_email", "email", "customer_email", "subject_reference")):
        return "present", result or "READ_COMPLETED"
    event = fields.get("event", "")
    if event.endswith("_completed") or event in EVENT_RECORD_TYPE:
        return "present", result or "READ_COMPLETED"
    return "unknown", result or None
