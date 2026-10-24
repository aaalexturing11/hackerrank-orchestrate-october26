"""Normalize JSON evidence. Catalog `result` values are observations, not workflow claims."""

from __future__ import annotations

import json
from pathlib import Path

from code.ingestion.normalize import (
    as_bool,
    as_int,
    as_text,
    bag_from_mapping,
    direct_identifiers_present,
    is_blank,
    make_observation,
    parse_time,
)
from code.models import EvidenceFile, Observation, ParseResult

COLLECTION_TYPE = {
    "customer_profiles": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY",
    "customer_analytics_reports": "ANALYTICS_PROFILE",
    "customer_analytics_profiles": "ANALYTICS_PROFILE",
    "customer_export_jobs": "USER_EXPORT",
    "connector_configurations": "DATA_FLOW",
    "security_audit_events": "SECURITY_AUDIT_LOG",
    "backup_catalog": "BACKUP_ARCHIVE",
    "support_conversations": "SUPPORT_MESSAGE",
    "ticket_attachments": "SUPPORT_ATTACHMENT",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
    "retained_order_records": "LEGAL_HOLD_RECORD",
}


def parse_json_file(evidence: EvidenceFile, path: Path) -> ParseResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    observations: list[Observation] = []
    warnings: list[str] = []
    if isinstance(payload, dict) and isinstance(payload.get("snapshots"), list):
        observations.extend(_snapshots(evidence, payload))
    elif isinstance(payload, dict) and isinstance(payload.get("service_exports"), dict):
        observations.extend(_service_exports(evidence, payload["service_exports"]))
    elif isinstance(payload, dict) and isinstance(payload.get("records"), list):
        observations.extend(_record_list(evidence, payload))
    else:
        warnings.append("JSON root is not a known evidence shape; no observations emitted")
        return ParseResult(
            file_id=evidence.file_id,
            path=str(path),
            kind="json",
            status="partial",
            observations=[],
            warnings=warnings,
        )
    return ParseResult(
        file_id=evidence.file_id,
        path=str(path),
        kind="json",
        status="parsed",
        observations=observations,
        warnings=warnings,
    )


def _snapshots(evidence: EvidenceFile, payload: dict) -> list[Observation]:
    observations: list[Observation] = []
    for snap_index, snapshot in enumerate(payload.get("snapshots") or []):
        if not isinstance(snapshot, dict):
            continue
        system_id = as_text(snapshot.get("data_store")) or "unspecified"
        collection = as_text(snapshot.get("collection"))
        record_type = COLLECTION_TYPE.get(collection or "", collection)
        observed = parse_time(snapshot.get("captured_at")) or evidence.captured_at
        records = snapshot.get("records") or []
        if not isinstance(records, list):
            continue
        for row_index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            observations.append(
                _from_record(
                    evidence=evidence,
                    record=record,
                    system_id=system_id,
                    record_type=record_type,
                    observed_at=parse_time(record.get("updated_at")) or parse_time(record.get("observed_at")) or observed,
                    locator=f"{evidence.file_id}:snapshots[{snap_index}].records[{row_index}]",
                )
            )
    return observations


def _service_exports(evidence: EvidenceFile, exports: dict) -> list[Observation]:
    observations: list[Observation] = []
    for system_id, body in exports.items():
        if not isinstance(body, dict):
            continue
        for collection, rows in body.items():
            if not isinstance(rows, list):
                continue
            for index, record in enumerate(rows):
                if not isinstance(record, dict):
                    continue
                observations.append(
                    _from_record(
                        evidence=evidence,
                        record=record,
                        system_id=str(system_id),
                        record_type=_export_collection_type(str(collection), record),
                        observed_at=parse_time(record.get("observed_at")) or evidence.captured_at,
                        locator=f"{evidence.file_id}:service_exports.{system_id}.{collection}[{index}]",
                    )
                )
    return observations


def _export_collection_type(collection: str, record: dict) -> str | None:
    mapping = {
        "profile_lookups": "USER_PROFILE",
        "profiles": "ANALYTICS_PROFILE",
        "restore_entries": "BACKUP_ARCHIVE",
        "exports": "USER_EXPORT",
        "connectors": "DATA_FLOW",
        "index_queries": "SEARCH_INDEX_ENTRY",
        "audit_records": "SECURITY_AUDIT_LOG",
        "tickets": "SUPPORT_MESSAGE",
    }
    return mapping.get(collection, as_text(record.get("record_type")))


def _record_list(evidence: EvidenceFile, payload: dict) -> list[Observation]:
    observations: list[Observation] = []
    collection = as_text(payload.get("collection"))
    default_type = COLLECTION_TYPE.get(collection or "", collection)
    system_default = as_text(payload.get("source")) or as_text(payload.get("origin")) or evidence.origin
    for index, record in enumerate(payload.get("records") or []):
        if not isinstance(record, dict):
            continue
        record_type = as_text(record.get("record_type")) or default_type
        system_id = as_text(record.get("system")) or system_default or "unspecified"
        observations.append(
            _from_record(
                evidence=evidence,
                record=record,
                system_id=system_id,
                record_type=record_type,
                observed_at=parse_time(record.get("recorded_at"))
                or parse_time(record.get("captured_at"))
                or parse_time(record.get("observed_at"))
                or evidence.captured_at,
                locator=f"{evidence.file_id}:records[{index}]",
            )
        )
    return observations


def _from_record(
    *,
    evidence: EvidenceFile,
    record: dict,
    system_id: str,
    record_type: str | None,
    observed_at: datetime | None,
    locator: str,
) -> Observation:
    resource_id = as_text(record.get("resource_id")) or ""
    fields = _flatten(record)
    bag = bag_from_mapping(fields)
    result = (as_text(record.get("result")) or "").upper()
    status_code = as_int(record.get("status_code"))
    presence, token, limitation, confidence = _presence(record, result, status_code)
    exposed = direct_identifiers_present(bag, fields)
    anonymized = None
    redacted = None
    if result == "ANONYMIZED":
        anonymized = True
        exposed = False
    elif result == "REDACTED":
        redacted = True
        exposed = False
    elif result == "IDENTIFIABLE":
        exposed = True
    elif presence == "present" and _schema_has_direct_fields(record) and not exposed and not bag.user_ids:
        anonymized = True
    flow_enabled = as_bool(record.get("enabled"))
    if result == "DISABLED":
        flow_enabled = False
    elif result == "ACTIVE" and record_type == "DATA_FLOW":
        flow_enabled = True
    restore_blocked = None
    if "restore_allowed" in record and as_bool(record.get("restore_allowed")) is not None:
        restore_blocked = not bool(as_bool(record.get("restore_allowed")))
    elif result == "BLOCKED":
        restore_blocked = True
    elif result == "ACTIVE" and record_type == "BACKUP_ARCHIVE":
        restore_blocked = False
    if record_type == "ACCOUNT_TOMBSTONE":
        # A tombstone row is present. Direct identifiers still on it are exposure, not absence.
        presence = "present"
        if exposed:
            redacted = False
        elif not exposed:
            redacted = True
    return make_observation(
        evidence_id=evidence.file_id,
        system_id=system_id,
        resource_id=resource_id,
        observed_at=observed_at,
        captured_at=evidence.captured_at,
        record_type=record_type,
        replica_role="unspecified",
        replica_name=None,
        presence=presence,
        identifiers=bag,
        identifiers_exposed=exposed if presence == "present" else None,
        source_locator=locator,
        limitations=limitation,
        confidence=confidence,
        result_token=token,
        anonymized=anonymized,
        redacted=redacted,
        flow_enabled=flow_enabled,
        restore_blocked=restore_blocked,
        retention_until=parse_time(record.get("retention_until")),
    )


def _schema_has_direct_fields(record: dict) -> bool:
    return any(key in record for key in ("email", "phone", "email_hash", "full_name", "name"))


def _presence(record: dict, result: str, status_code: int | None) -> tuple[str, str | None, str, str]:
    profile = record.get("profile")
    if status_code == 404 or (status_code == 200 and profile is None and "profile" in record and is_blank(profile)):
        return "absent", "HTTP_404" if status_code == 404 else result or "EMPTY_PROFILE", "explicit lookup result", "high"
    if status_code == 404:
        return "absent", "HTTP_404", "explicit lookup result", "high"
    if result in {"NOT_FOUND"}:
        return "absent", result, "explicit catalog result", "high"
    if result in {"FOUND", "IDENTIFIABLE", "ANONYMIZED", "REDACTED", "ACTIVE", "BLOCKED", "DISABLED"}:
        return "present", result, "explicit catalog or export result", "high"
    if "profile" in record and profile is None and status_code is None:
        return "absent", "NULL_PROFILE", "profile field is null", "medium"
    if as_text(record.get("resource_id")):
        return "present", result or None, "record object is present in the extract", "high"
    return "unknown", result or None, "record has no resource_id", "low"


def _flatten(record: dict) -> dict[str, object]:
    flat: dict[str, object] = {}
    for key, value in record.items():
        if isinstance(value, dict):
            for inner_key, inner_value in value.items():
                flat.setdefault(inner_key, inner_value)
            flat[key] = value
        else:
            flat[key] = value
    document = record.get("document")
    if isinstance(document, dict):
        for key, value in document.items():
            flat.setdefault(key, value)
    profile = record.get("profile")
    if isinstance(profile, dict):
        for key, value in profile.items():
            flat.setdefault(key, value)
    return flat
