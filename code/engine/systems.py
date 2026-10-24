"""Canonical system ids.

Raw source names stay on the observation. Steps use this map. Aliases are
exact source labels that are not themselves canonical systems. Known replica
system ids stay distinct. A resource prefix is used only when the source did
not name a system.
"""

from __future__ import annotations

from code.config import KNOWN_SYSTEMS

EXPLICIT_SYSTEM_ALIASES = {
    "support_replica": "support_platform",
    "profile_service": "account_service",
}

# Longest prefixes first. Applied only when no system name was supplied.
RESOURCE_PREFIX_SYSTEM = (
    ("audit_record_", "security_service"),
    ("email_delivery_", "email_delivery_service"),
    ("data_flow_", "integration_service"),
    ("legal_hold_", "legal_service"),
    ("tombstone_", "identity_service"),
    ("analytics_", "analytics_platform"),
    ("marketing_", "marketing_platform"),
    ("account_", "account_service"),
    ("search_", "search_service"),
    ("support_", "support_platform"),
    ("backup_", "backup_service"),
    ("export_", "export_service"),
    ("cache_", "cache_service"),
    ("object_", "object_storage"),
)


def canonical_system(system_id: str, resource_id: str = "") -> str:
    if system_id in KNOWN_SYSTEMS:
        return system_id
    if system_id in EXPLICIT_SYSTEM_ALIASES:
        return EXPLICIT_SYSTEM_ALIASES[system_id]
    if system_id in {"", "unspecified"}:
        return system_for_resource(resource_id) or "unspecified"
    return system_id


def system_for_resource(resource_id: str) -> str | None:
    for prefix, system_id in RESOURCE_PREFIX_SYSTEM:
        if resource_id.startswith(prefix):
            return system_id
    return None
