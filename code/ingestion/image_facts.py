"""Facts read from the eleven screenshots.

Each record is a visually confirmed field. Relationships that were not on the
screen are not filled in here. Capture time comes from the evidence manifest
when the parser builds the observation.
"""

from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


# file_id -> list of observation field dicts
IMAGE_FACTS: dict[str, list[dict[str, object]]] = {
    "evidence_04": [
        {
            "system_id": "account_service",
            "resource_id": "account_5762",
            "record_type": "USER_PROFILE",
            "presence": "present",
            "observed_at": _time("2026-09-24T00:14:00Z"),
            "emails": ("haruka.s1838@zoho.com",),
            "phones": ("+81 90 7610 2507",),
            "user_ids": ("user_11",),
            "names": ("Haruka Sato",),
            "identifiers_exposed": True,
            "limitations": "account admin console shows the profile live",
        }
    ],
    "evidence_09": [
        {
            "system_id": "search_service",
            "resource_id": "search_428",
            "record_type": "SEARCH_INDEX_ENTRY",
            "presence": "present",
            "observed_at": _time("2026-09-01T05:58:21Z"),
            "emails": ("g.silva76@gmail.com",),
            "user_ids": ("user_13",),
            "names": ("Gabriel Silva",),
            "identifiers_exposed": True,
            "limitations": "search console hit; a similar address on search_1874 is a different row",
        },
        {
            "system_id": "search_service",
            "resource_id": "search_1874",
            "record_type": "SEARCH_INDEX_ENTRY",
            "presence": "present",
            "observed_at": _time("2026-09-01T05:55:03Z"),
            "emails": ("g.silva76.jr@gmail.com",),
            "identifiers_exposed": True,
            "limitations": "search hit with no customer reference; not joined to search_428",
        },
    ],
    "evidence_14": [
        {
            "system_id": "integration_service",
            "resource_id": "data_flow_1121",
            "record_type": "DATA_FLOW",
            "presence": "present",
            "observed_at": _time("2026-08-07T07:59:42Z"),
            "emails": ("jain.aditi@gmail.com",),
            "identifiers_exposed": True,
            "flow_enabled": True,
            "limitations": "connector console shows continuous sync",
        },
        {
            "system_id": "integration_service",
            "resource_id": "data_flow_9846",
            "record_type": "DATA_FLOW",
            "presence": "present",
            "observed_at": _time("2026-08-07T07:59:36Z"),
            "emails": ("lucia-torres@gmail.com",),
            "identifiers_exposed": True,
            "flow_enabled": True,
            "limitations": "connector console shows continuous sync",
        },
    ],
    "evidence_19": [
        {
            "system_id": "analytics_platform",
            "resource_id": "analytics_7438",
            "record_type": "ANALYTICS_PROFILE",
            "presence": "present",
            "observed_at": _time("2026-07-13T14:22:00Z"),
            "emails": ("darwish.omar@icloud.com",),
            "user_ids": ("user_20",),
            "names": ("Omar Darwish",),
            "identifiers_exposed": True,
            "anonymized": False,
            "limitations": "analytics profile view still shows the customer's name and email",
        }
    ],
    "evidence_23": [
        {
            "system_id": "export_service",
            "resource_id": "export_1261",
            "record_type": "USER_EXPORT",
            "presence": "present",
            "observed_at": _time("2026-06-20T14:18:00Z"),
            "emails": ("marcus.lee@northstar.shop",),
            "identifiers_exposed": True,
            "limitations": "export job listed as collecting",
        },
        {
            "system_id": "export_service",
            "resource_id": "export_1260",
            "record_type": "USER_EXPORT",
            "presence": "present",
            "observed_at": _time("2026-06-18T06:42:00Z"),
            "emails": ("ingrid.dahl@outlook.com",),
            "identifiers_exposed": True,
            "limitations": "export package listed as ready and includes profile, orders, and addresses",
        },
        {
            "system_id": "export_service",
            "resource_id": "export_1259",
            "record_type": "USER_EXPORT",
            "presence": "present",
            "observed_at": _time("2026-06-17T11:03:00Z"),
            "emails": ("sara.kim@northstar.shop",),
            "identifiers_exposed": True,
            "limitations": "export job listed as packaging",
        },
        {
            "system_id": "export_service",
            "resource_id": "export_1258",
            "record_type": "USER_EXPORT",
            "presence": "present",
            "observed_at": _time("2026-06-16T09:27:00Z"),
            "emails": ("daniel.park@northstar.shop",),
            "identifiers_exposed": True,
            "limitations": "export package listed as ready",
        },
    ],
    "evidence_28": [
        {
            "system_id": "support_platform",
            "resource_id": "support_1034",
            "record_type": "SUPPORT_MESSAGE",
            "presence": "present",
            "observed_at": _time("2026-05-22T09:12:00Z"),
            "emails": ("kagyeman8947@fastmail.com",),
            "names": ("Kofi Agyeman",),
            "identifiers_exposed": True,
            "shared_context": True,
            "limitations": "ticket conversation includes the customer and an assigned agent",
        }
    ],
    "evidence_32": [
        {
            "system_id": "backup_service",
            "resource_id": "backup_9291",
            "record_type": "BACKUP_ARCHIVE",
            "presence": "present",
            "observed_at": _time("2026-04-26T02:00:00Z"),
            "emails": ("bluepeakco@outlook.com",),
            "identifiers_exposed": True,
            "restore_blocked": False,
            "limitations": "recovery console lists the archive; restore jobs are available on this screen",
        },
        {
            "system_id": "backup_service",
            "resource_id": "backup_9288",
            "record_type": "BACKUP_ARCHIVE",
            "presence": "present",
            "observed_at": _time("2026-04-26T02:00:00Z"),
            "emails": ("miller.logistics@company.com",),
            "identifiers_exposed": True,
            "restore_blocked": False,
            "limitations": "activity on the same screen says this archive was restored",
        },
        {
            "system_id": "backup_service",
            "resource_id": "backup_9287",
            "record_type": "BACKUP_ARCHIVE",
            "presence": "present",
            "observed_at": _time("2026-04-26T02:00:00Z"),
            "emails": ("areed1433@gmail.com",),
            "identifiers_exposed": True,
            "restore_blocked": False,
            "retention_until": _time("2026-07-26T00:00:00Z"),
            "limitations": "recovery console lists the archive and its retention end",
        },
        {
            "system_id": "backup_service",
            "resource_id": "backup_9286",
            "record_type": "BACKUP_ARCHIVE",
            "presence": "present",
            "observed_at": _time("2026-04-26T02:00:00Z"),
            "emails": ("summit-retail@company.com",),
            "identifiers_exposed": True,
            "restore_blocked": False,
            "limitations": "recovery console lists the archive",
        },
    ],
    "evidence_37": [
        {
            "system_id": "security_service",
            "resource_id": resource_id,
            "record_type": "SECURITY_AUDIT_LOG",
            "presence": "present",
            "observed_at": _time("2026-08-25T04:03:00Z"),
            "user_ids": ("user_03",),
            "identifiers_exposed": False,
            "limitations": "security console lists a signed account event for user_03",
        }
        for resource_id in (
            "audit_record_001",
            "audit_record_002",
            "audit_record_003",
            "audit_record_004",
            "audit_record_005",
            "audit_record_006",
        )
    ],
    "evidence_42": [
        {
            "system_id": "identity_service",
            "resource_id": "user_17",
            "record_type": "CUSTOMER_REFERENCE",
            "presence": "present",
            "observed_at": _time("2026-03-10T07:18:00Z"),
            "user_ids": ("user_17",),
            "identifiers_exposed": False,
            "limitations": "retained customer reference shows user_17 only; no tombstone id or direct contact fields are on the screen",
        }
    ],
    "evidence_46": [
        {
            "system_id": "object_storage",
            "resource_id": name,
            "record_type": "STORED_OBJECT",
            "presence": "present",
            "observed_at": _time("2026-02-12T18:42:00Z"),
            "identifiers_exposed": False,
            "limitations": "object browser shows the file name; it does not show a customer id",
        }
        for name in (
            "delivery_confirmation_19.pdf",
            "delivery_confirmation_20.pdf",
            "return_label_4821.pdf",
            "return_label_4876.pdf",
            "invoice_N5-10493.pdf",
            "parcel_damage_7713.jpg",
            "customer_export_2026-02-10.zip",
            "customer_export_2026-02-12.zip",
        )
    ],
    "evidence_60": [
        {
            "system_id": "marketing_platform",
            "resource_id": "marketing_001",
            "record_type": "MARKETING_PROFILE",
            "presence": "present",
            "observed_at": _time("2026-09-15T23:40:00Z"),
            "emails": ("sj.park@naver.com",),
            "phones": ("+82 10-5837-9451",),
            "names": ("Soo-jin Park",),
            "identifiers_exposed": True,
            "limitations": "marketing profile is live and email opt-in is yes",
        }
    ],
}
