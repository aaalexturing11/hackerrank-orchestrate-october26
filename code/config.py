"""Paths and ordering settings for the deletion-audit foundation.

Resource and case-id ordering default to lexicographic comparison. Production
case ids are not zero-padded, so lexicographic order and numeric order differ.
The problem statement says "sorted by case_id" and "resource_id in ascending
order" without defining a numeric sort. Both comparisons are available to tests.
"""

from __future__ import annotations

from pathlib import Path

RESOURCE_SORT = "lexicographic"
CASE_ID_SORT = "lexicographic"

KNOWN_SYSTEMS = frozenset(
    {
        "account_service",
        "search_service",
        "support_platform",
        "analytics_platform",
        "security_service",
        "integration_service",
        "backup_service",
        "export_service",
        "identity_service",
        "cache_service",
        "email_delivery_service",
        "marketing_platform",
        "legal_service",
        "archive_service",
        "object_store",
        "object_storage",
        "privacy_case_management",
        "account_replication_cluster",
        "account_failover_replica",
    }
)


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "AGENTS.md").is_file() and (candidate / "dataset").is_dir():
            return candidate
    raise RuntimeError("Could not locate the repository root from code/config.py")


def dataset_dir() -> Path:
    return repo_root() / "dataset"
