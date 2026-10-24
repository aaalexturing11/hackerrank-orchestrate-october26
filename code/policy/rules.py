"""Deletion-rule lookup and the authoritative operation table.

The operation/state pairs come from problem_statement.md, "Allowed Operations".
They are not inferred from sample rows.
"""

from __future__ import annotations

from code.models import PolicyRule

PHASES = ("FINDING", "REMEDIATION", "VERIFICATION")

# Table order is the within-phase sort key.
OPERATION_ORDER = (
    "REPORT_REMAINING_RECORD",
    "REPORT_EXPOSED_PII",
    "REPORT_ACTIVE_DATA_FLOW",
    "REPORT_RESTORE_RISK",
    "DISABLE_DATA_FLOW",
    "BLOCK_RESTORE",
    "DELETE_RECORD",
    "REDACT_RECORD",
    "ANONYMIZE_RECORD",
    "VERIFY_RECORD_ABSENT",
    "VERIFY_RECORD_PRESENT",
    "VERIFY_RECORD_REDACTED",
    "VERIFY_RECORD_ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED",
    "VERIFY_RESTORE_BLOCKED",
)

ALLOWED_PAIRS = {
    ("FINDING", "REPORT_REMAINING_RECORD"): "PRESENT",
    ("FINDING", "REPORT_EXPOSED_PII"): "PRESENT",
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW"): "ACTIVE",
    ("FINDING", "REPORT_RESTORE_RISK"): "ACTIVE",
    ("REMEDIATION", "DISABLE_DATA_FLOW"): "DISABLED",
    ("REMEDIATION", "BLOCK_RESTORE"): "BLOCKED",
    ("REMEDIATION", "DELETE_RECORD"): "ABSENT",
    ("REMEDIATION", "REDACT_RECORD"): "REDACTED",
    ("REMEDIATION", "ANONYMIZE_RECORD"): "ANONYMIZED",
    ("VERIFICATION", "VERIFY_RECORD_ABSENT"): "ABSENT",
    ("VERIFICATION", "VERIFY_RECORD_PRESENT"): "PRESENT",
    ("VERIFICATION", "VERIFY_RECORD_REDACTED"): "REDACTED",
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED"): "ANONYMIZED",
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED"): "DISABLED",
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED"): "BLOCKED",
}

OPERATION_PHASE = {operation: phase for (phase, operation) in ALLOWED_PAIRS}
OPERATION_STATE = {operation: state for (_phase, operation), state in ALLOWED_PAIRS.items()}

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
REDACT_CATEGORIES = frozenset({"SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG", "ACCOUNT_TOMBSTONE"})
ANONYMIZE_CATEGORIES = frozenset({"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"})
RETAIN_CATEGORIES = frozenset({"SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD", "BACKUP_ARCHIVE"})


def rules_by_category(rules: list[PolicyRule]) -> dict[str, PolicyRule]:
    found: dict[str, PolicyRule] = {}
    for rule in rules:
        found[rule.data_category] = rule
    return found


def required_action(rules: list[PolicyRule], category: str) -> str | None:
    rule = rules_by_category(rules).get(category)
    if rule is None:
        return None
    return rule.required_action
