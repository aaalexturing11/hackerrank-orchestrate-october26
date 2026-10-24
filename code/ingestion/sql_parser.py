"""Read SQLite snapshot scripts in memory. The source files are not opened as databases."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from code.ingestion.normalize import (
    as_bool,
    as_text,
    bag_from_mapping,
    direct_identifiers_present,
    make_observation,
    parse_time,
    replica_role_from_name,
)
from code.models import EvidenceFile, Observation, ParseResult

TABLE_RECORD_TYPE = {
    "customer_profiles": "USER_PROFILE",
    "customer_profiles_primary": "USER_PROFILE",
    "customer_profiles_failover_replica": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY",
    "search_documents_primary": "SEARCH_INDEX_ENTRY",
    "customer_analytics_profiles": "ANALYTICS_PROFILE",
    "customer_exports": "USER_EXPORT",
    "support_records": "SUPPORT_MESSAGE",
    "security_audit_records": "SECURITY_AUDIT_LOG",
    "backup_restore_entries": "BACKUP_ARCHIVE",
    "connector_subscriptions": "DATA_FLOW",
    "retained_order_records": "LEGAL_HOLD_RECORD",
    "security_audit_events": "SECURITY_AUDIT_LOG",
    "customer_analytics_reports": "ANALYTICS_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY",
    "customer_export_jobs": "USER_EXPORT",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
}


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def parse_sql_file(evidence: EvidenceFile, path: Path) -> ParseResult:
    script = path.read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    try:
        connection.row_factory = sqlite3.Row
        connection.executescript(script)
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        observations: list[Observation] = []
        present_by_table: dict[str, set[str]] = {}
        roles: dict[str, str] = {}
        for table in tables:
            if table == "snapshot_scope":
                continue
            role = replica_role_from_name(table)
            roles[table] = role
            columns = [info[1] for info in connection.execute(f"PRAGMA table_info({_quote(table)})")]
            if "resource_id" not in columns:
                continue
            present_ids: set[str] = set()
            rows = connection.execute(f"SELECT * FROM {_quote(table)}")
            for index, row in enumerate(rows, start=1):
                mapping = {key: row[key] for key in row.keys()}
                resource_id = as_text(mapping.get("resource_id"))
                if resource_id is None:
                    continue
                present_ids.add(resource_id)
                observations.append(
                    _row_observation(
                        evidence=evidence,
                        table=table,
                        role=role,
                        mapping=mapping,
                        locator=f"{evidence.file_id}:{table}:{index}",
                    )
                )
            present_by_table[table] = present_ids
        observations.extend(_paired_absences(evidence, present_by_table, roles))
        warnings: list[str] = []
        if not observations and present_by_table is not None:
            warnings.append("snapshot tables contain no resource rows; an empty extract is not proof of absence")
    finally:
        connection.close()
    return ParseResult(
        file_id=evidence.file_id,
        path=str(path),
        kind="sql",
        status="parsed",
        observations=observations,
        warnings=warnings,
    )


def _row_observation(
    *,
    evidence: EvidenceFile,
    table: str,
    role: str,
    mapping: dict[str, object],
    locator: str,
) -> Observation:
    record_json = mapping.get("record_json")
    fields: dict[str, object] = {key: value for key, value in mapping.items() if key != "record_json"}
    if isinstance(record_json, str) and record_json.strip().startswith("{"):
        import json

        try:
            nested = json.loads(record_json)
        except json.JSONDecodeError:
            nested = None
        if isinstance(nested, dict):
            fields.update(nested)
    bag = bag_from_mapping(fields)
    exposed = direct_identifiers_present(bag, fields)
    anonymized = None
    redacted = None
    if _direct_fields_present(fields) and not exposed and not bag.user_ids:
        anonymized = True
    record_type = TABLE_RECORD_TYPE.get(table)
    if record_type is None:
        collection = as_text(mapping.get("collection_name"))
        record_type = TABLE_RECORD_TYPE.get(collection or "", collection)
    system_id = as_text(mapping.get("origin_system")) or _system_for_table(table)
    flow_enabled = as_bool(fields.get("enabled"))
    restore_allowed = as_bool(fields.get("restore_allowed"))
    restore_blocked = None if restore_allowed is None else not restore_allowed
    observed_at = parse_time(fields.get("updated_at")) or parse_time(fields.get("captured_at"))
    retention_until = parse_time(fields.get("retention_until"))
    status = as_text(fields.get("account_status"))
    return make_observation(
        evidence_id=evidence.file_id,
        system_id=system_id or "unspecified",
        resource_id=str(mapping.get("resource_id")),
        observed_at=observed_at or evidence.captured_at,
        captured_at=evidence.captured_at,
        record_type=record_type,
        replica_role=role,
        replica_name=table,
        presence="present",
        identifiers=bag,
        identifiers_exposed=exposed,
        source_locator=locator,
        limitations="row exists in this snapshot table",
        confidence="high",
        result_token=status,
        anonymized=anonymized,
        redacted=redacted,
        flow_enabled=flow_enabled,
        restore_blocked=restore_blocked,
        retention_until=retention_until,
    )


def _direct_fields_present(fields: dict[str, object]) -> bool:
    return any(key in fields for key in ("email", "phone", "email_hash", "full_name"))


def _system_for_table(table: str) -> str:
    lowered = table.lower()
    if "search" in lowered:
        return "search_service"
    if "support" in lowered:
        return "support_platform"
    if "analytics" in lowered:
        return "analytics_platform"
    if "export" in lowered:
        return "export_service"
    if "security" in lowered or "audit" in lowered:
        return "security_service"
    if "backup" in lowered:
        return "backup_service"
    if "connector" in lowered:
        return "integration_service"
    if "profile" in lowered:
        return "account_service"
    return "unspecified"


def _paired_absences(
    evidence: EvidenceFile,
    present_by_table: dict[str, set[str]],
    roles: dict[str, str],
) -> list[Observation]:
    primary_tables = [name for name, role in roles.items() if role == "primary" and name in present_by_table]
    if len(primary_tables) != 1:
        return []
    primary = primary_tables[0]
    primary_ids = present_by_table[primary]
    observations: list[Observation] = []
    for table, ids in present_by_table.items():
        if table == primary:
            continue
        only_replica = ids - primary_ids
        only_primary = primary_ids - ids
        for resource_id in sorted(only_replica):
            observations.append(_absence(evidence, primary, "primary", resource_id, table))
        for resource_id in sorted(only_primary):
            observations.append(_absence(evidence, table, roles[table], resource_id, primary))
    return observations


def _absence(
    evidence: EvidenceFile,
    table: str,
    role: str,
    resource_id: str,
    counterpart: str,
) -> Observation:
    return make_observation(
        evidence_id=evidence.file_id,
        system_id=_system_for_table(table),
        resource_id=resource_id,
        observed_at=evidence.captured_at,
        captured_at=evidence.captured_at,
        record_type=TABLE_RECORD_TYPE.get(table),
        replica_role=role,
        replica_name=table,
        presence="absent",
        identifiers=bag_from_mapping({}),
        identifiers_exposed=None,
        source_locator=f"{evidence.file_id}:{table}:paired-with:{counterpart}",
        limitations=(
            "paired snapshot omission inside this file only; "
            "resources never listed in either table are not absences"
        ),
        confidence="medium",
        result_token="PAIRED_OMISSION",
    )
