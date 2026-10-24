"""Map an observed record to the deletion-rule treatment.

Categories come from record types and collection names. A resource prefix is
not a category. Direct identifiers are name, email, phone, and email hash.
A stable user id may remain on a tombstone and on a retained security log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from code.models import ResourceState

COLLECTION_CATEGORY = {
    "USER_PROFILE": "USER_PROFILE",
    "customer_profiles": "USER_PROFILE",
    "SEARCH_INDEX_ENTRY": "SEARCH_INDEX_ENTRY",
    "customer_search_documents": "SEARCH_INDEX_ENTRY",
    "search_documents_primary": "SEARCH_INDEX_ENTRY",
    "ANALYTICS_PROFILE": "ANALYTICS_PROFILE",
    "customer_analytics_profiles": "ANALYTICS_PROFILE",
    "customer_analytics_reports": "ANALYTICS_PROFILE",
    "analytics_profile_read": "ANALYTICS_PROFILE",
    "analytics_profile_read_completed": "ANALYTICS_PROFILE",
    "CONTACT_LOOKUP": "MARKETING_PROFILE",
    "SUPPORT_MESSAGE": "SUPPORT_MESSAGE",
    "support_records": "SUPPORT_MESSAGE",
    "support_conversations": "SUPPORT_MESSAGE",
    "SUPPORT_ATTACHMENT": "SUPPORT_ATTACHMENT",
    "ticket_attachments": "SUPPORT_ATTACHMENT",
    "USER_EXPORT": "USER_EXPORT",
    "customer_exports": "USER_EXPORT",
    "customer_export_jobs": "USER_EXPORT",
    "DATA_FLOW": "DATA_FLOW",
    "connector_subscriptions": "DATA_FLOW",
    "connector_configurations": "DATA_FLOW",
    "BACKUP_ARCHIVE": "BACKUP_ARCHIVE",
    "backup_restore_entries": "BACKUP_ARCHIVE",
    "backup_catalog": "BACKUP_ARCHIVE",
    "SECURITY_AUDIT_LOG": "SECURITY_AUDIT_LOG",
    "security_audit_events": "SECURITY_AUDIT_LOG",
    "security_audit_records": "SECURITY_AUDIT_LOG",
    "ACCOUNT_TOMBSTONE": "ACCOUNT_TOMBSTONE",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
    "LEGAL_HOLD_RECORD": "LEGAL_HOLD_RECORD",
    "retained_order_records": "LEGAL_HOLD_RECORD",
    "MARKETING_PROFILE": "MARKETING_PROFILE",
    "EMAIL_DELIVERY_LOG": "EMAIL_DELIVERY_LOG",
    "CACHE_ENTRY": "CACHE_ENTRY",
    "SECONDARY_IDENTIFIER": "SECONDARY_IDENTIFIER",
    "PRODUCT_TELEMETRY": "PRODUCT_TELEMETRY",
}

DELETE_CATEGORIES = frozenset(
    {
        "USER_PROFILE",
        "SECONDARY_IDENTIFIER",
        "SEARCH_INDEX_ENTRY",
        "CACHE_ENTRY",
        "SUPPORT_ATTACHMENT",
        "USER_EXPORT",
        "MARKETING_PROFILE",
    }
)


@dataclass(frozen=True)
class Treatment:
    category: str
    action: str
    compliant: bool
    finding_operation: str | None
    remediation_operation: str | None
    verification_operation: str


def category_for(record_type: str | None) -> str | None:
    if not record_type:
        return None
    return COLLECTION_CATEGORY.get(record_type)


def decide(state: ResourceState, audit_at: datetime) -> Treatment | None:
    category = category_for(state.record_type)
    if category is None or state.presence in {"unknown", "conflict"}:
        return None
    if category == "DATA_FLOW":
        return _flow(state)
    if category == "BACKUP_ARCHIVE":
        return _backup(state)
    if category == "SECURITY_AUDIT_LOG":
        return _security(state, audit_at)
    if category == "LEGAL_HOLD_RECORD":
        return _legal_hold(state, audit_at)
    if category == "ACCOUNT_TOMBSTONE":
        return _redact_target(state, category, exposed=_tombstone_exposed(state))
    if category in {"SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG"}:
        return _redact_target(state, category, exposed=_identifiers_exposed(state))
    if category in {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"}:
        return _anonymize_target(state, category)
    if category in DELETE_CATEGORIES:
        return _delete_target(state, category)
    return None


def _delete_target(state: ResourceState, category: str) -> Treatment | None:
    if state.presence == "present":
        return Treatment(category, "DELETE", False, "REPORT_REMAINING_RECORD", "DELETE_RECORD", "VERIFY_RECORD_ABSENT")
    if state.presence == "absent":
        return Treatment(category, "DELETE", True, None, None, "VERIFY_RECORD_ABSENT")
    return None


def _redact_target(state: ResourceState, category: str, *, exposed: bool) -> Treatment | None:
    if state.presence == "absent":
        return None
    if exposed:
        return Treatment(category, "REDACT", False, "REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED")
    return Treatment(category, "REDACT", True, None, None, "VERIFY_RECORD_REDACTED")


def _anonymize_target(state: ResourceState, category: str) -> Treatment | None:
    if state.presence == "absent":
        return Treatment(category, "ANONYMIZE", True, None, None, "VERIFY_RECORD_ANONYMIZED")
    if _still_attributable(state):
        return Treatment(category, "ANONYMIZE", False, "REPORT_EXPOSED_PII", "ANONYMIZE_RECORD", "VERIFY_RECORD_ANONYMIZED")
    return Treatment(category, "ANONYMIZE", True, None, None, "VERIFY_RECORD_ANONYMIZED")


def _flow(state: ResourceState) -> Treatment | None:
    if state.presence != "present" or state.flow_enabled is None:
        return None
    if state.flow_enabled:
        return Treatment("DATA_FLOW", "DISABLE", False, "REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "VERIFY_DATA_FLOW_DISABLED")
    return Treatment("DATA_FLOW", "DISABLE", True, None, None, "VERIFY_DATA_FLOW_DISABLED")


def _backup(state: ResourceState) -> Treatment | None:
    if state.presence != "present" or state.restore_blocked is None:
        return None
    if state.restore_blocked:
        return Treatment("BACKUP_ARCHIVE", "RETAIN", True, None, None, "VERIFY_RESTORE_BLOCKED")
    return Treatment("BACKUP_ARCHIVE", "RETAIN", False, "REPORT_RESTORE_RISK", "BLOCK_RESTORE", "VERIFY_RESTORE_BLOCKED")


def _security(state: ResourceState, audit_at: datetime) -> Treatment | None:
    if state.presence != "present":
        return None
    if state.retention_until is not None and state.retention_until < audit_at:
        return None
    return Treatment("SECURITY_AUDIT_LOG", "RETAIN", True, None, None, "VERIFY_RECORD_PRESENT")


def _legal_hold(state: ResourceState, audit_at: datetime) -> Treatment | None:
    if state.presence != "present":
        return None
    if state.retention_until is not None and state.retention_until < audit_at:
        return None
    exposed = _identifiers_exposed(state)
    if exposed:
        return Treatment("LEGAL_HOLD_RECORD", "REDACT", False, "REPORT_EXPOSED_PII", "REDACT_RECORD", "VERIFY_RECORD_REDACTED")
    return Treatment("LEGAL_HOLD_RECORD", "RETAIN", True, None, None, "VERIFY_RECORD_PRESENT")


def _identifiers_exposed(state: ResourceState) -> bool:
    if state.redacted is True or state.anonymized is True:
        return False
    if state.identifiers_exposed is False and state.redacted is not False:
        return False
    return bool(state.identifiers_exposed)


def _tombstone_exposed(state: ResourceState) -> bool:
    if state.redacted is True:
        return False
    return bool(state.identifiers_exposed)


def _still_attributable(state: ResourceState) -> bool:
    if state.anonymized is True:
        return False
    return bool(state.identifiers_exposed or state.linkable)
