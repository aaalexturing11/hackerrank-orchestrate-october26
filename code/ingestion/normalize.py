"""Shared helpers for turning raw evidence fields into observations."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from code.models import IdentifierBag, Observation

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
USER_RE = re.compile(r"\buser_\d+\b")
PHONE_RE = re.compile(r"\+\d[\d\-\s()]{6,}\d")
HASH_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
RESOURCE_RE = re.compile(
    r"\b(?:account|search|support|analytics|audit_record|export|data_flow|backup|tombstone|"
    r"legal_hold|cache|marketing|email_delivery|object)_\d+\b"
)

EMPTY_TOKENS = frozenset({"", "null", "none", "n/a", "nil"})


def is_blank(value: object) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text.casefold() in EMPTY_TOKENS


def as_text(value: object) -> str | None:
    if is_blank(value):
        return None
    return str(value).strip()


def parse_time(value: object) -> datetime | None:
    text = as_text(value)
    if text is None:
        return None
    if text.endswith("Z"):
        try:
            return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = as_text(value)
    if text is None:
        return None
    lowered = text.casefold()
    if lowered in {"1", "true", "yes", "enabled", "active"}:
        return True
    if lowered in {"0", "false", "no", "disabled", "blocked"}:
        return False
    return None


def as_int(value: object) -> int | None:
    text = as_text(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _nested_items(value: object) -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []

    def walk(item: object) -> None:
        if isinstance(item, dict):
            for key, inner in item.items():
                found.append((str(key), inner))
                walk(inner)
        elif isinstance(item, list):
            for inner in item:
                walk(inner)

    walk(value)
    return found


def bag_from_mapping(fields: dict[str, object]) -> IdentifierBag:
    emails: list[str] = []
    phones: list[str] = []
    hashes: list[str] = []
    users: list[str] = []
    names: list[str] = []
    email_keys = {
        "email",
        "owner_email",
        "customer_email",
        "requester_email",
        "lookup_key",
        "match_key",
        "subject_key",
        "subject_reference",
        "correlation_key",
        "matched_value",
        "owner_key",
    }
    phone_keys = {"phone", "owner_phone", "requester_phone", "customer_phone"}
    hash_keys = {"email_hash", "correlation_key"}
    user_keys = {
        "user_id",
        "customer_reference",
        "subject_reference",
        "subject_ref",
        "lookup_key",
        "correlation_key",
        "matched_value",
        "owner_key",
    }
    name_keys = {"name", "full_name", "display_name", "requester_name"}
    for key, value in _nested_items(fields):
        if isinstance(value, (dict, list)) or is_blank(value):
            continue
        text = str(value).strip()
        key_name = key.lower()
        if key_name in email_keys:
            emails.extend(EMAIL_RE.findall(text))
        if key_name in phone_keys or (key_name in email_keys and text.startswith("+")):
            phones.extend(PHONE_RE.findall(text))
        if key_name in hash_keys and HASH_RE.fullmatch(text):
            hashes.append(text.lower())
        if key_name in user_keys:
            users.extend(USER_RE.findall(text))
        if key_name in name_keys and not EMAIL_RE.fullmatch(text) and not USER_RE.fullmatch(text):
            names.append(text)
    return IdentifierBag(
        emails=tuple(dict.fromkeys(emails)),
        phones=tuple(dict.fromkeys(phones)),
        email_hashes=tuple(dict.fromkeys(hashes)),
        user_ids=tuple(dict.fromkeys(users)),
        names=tuple(dict.fromkeys(names)),
    )


def direct_identifiers_present(bag: IdentifierBag, fields: dict[str, object] | None = None) -> bool:
    if bag.emails or bag.phones or bag.email_hashes or bag.names:
        return True
    if fields:
        for key in ("email", "phone", "email_hash", "full_name", "requester_email", "owner_email"):
            if key in fields and not is_blank(fields.get(key)):
                return True
    return False


def make_observation(
    *,
    evidence_id: str,
    system_id: str,
    resource_id: str,
    observed_at: datetime | None,
    captured_at: datetime | None,
    record_type: str | None,
    replica_role: str,
    replica_name: str | None,
    presence: str,
    identifiers: IdentifierBag,
    identifiers_exposed: bool | None,
    source_locator: str,
    limitations: str,
    confidence: str,
    result_token: str | None = None,
    is_claim: bool = False,
    anonymized: bool | None = None,
    redacted: bool | None = None,
    flow_enabled: bool | None = None,
    restore_blocked: bool | None = None,
    retention_until: datetime | None = None,
    sole_subject: bool | None = None,
    shared_context: bool | None = None,
) -> Observation:
    return Observation(
        evidence_id=evidence_id,
        system_id=system_id or "unspecified",
        resource_id=resource_id,
        observed_at=observed_at,
        captured_at=captured_at,
        record_type=record_type,
        replica_role=replica_role,
        replica_name=replica_name,
        presence=presence,
        identifiers=identifiers,
        identifiers_exposed=identifiers_exposed,
        anonymized=anonymized,
        redacted=redacted,
        flow_enabled=flow_enabled,
        restore_blocked=restore_blocked,
        retention_until=retention_until,
        result_token=result_token,
        is_claim=is_claim,
        source_locator=source_locator,
        limitations=limitations,
        confidence=confidence,
        sole_subject=sole_subject,
        shared_context=shared_context,
    )


def replica_role_from_name(name: str) -> str:
    lowered = name.lower()
    if "primary" in lowered:
        return "primary"
    if "failover" in lowered:
        return "failover"
    if "reporting" in lowered:
        return "reporting"
    if "regional" in lowered or "_ap_" in lowered or "_eu_" in lowered or "replica_ap" in lowered or "replica_eu" in lowered:
        return "regional"
    if "read_replica" in lowered or lowered.endswith("read_replica"):
        return "read"
    if "replica" in lowered:
        return "read"
    return "unspecified"
