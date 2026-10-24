"""Resolve a subject from current identities and audit history.

Joins use email, phone, email hash, and user_id. Names are never join keys.
Resource ids are attached only from evidence observations or from activity rows
that explicitly name both a resource and a matching user. Account ids are not
invented by padding or numeric similarity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from code.ingestion.csv_loader import Dataset
from code.models import ActivityRecord, IdentifierBag, IdentityChange, IdentityLink, IdentitySnapshot, Observation

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
USER_RE = re.compile(r"\buser_\d+\b")
LINK_RE = re.compile(
    r"linked\s+\S+\s+\([^)]+\)\s+to\s+(\S+)\s+and\s+(user_\d+)",
    re.IGNORECASE,
)
SOLE_RE = re.compile(
    r"belongs only to\s+(\S+)\s+and\s+(user_\d+)",
    re.IGNORECASE,
)


def fold_email(value: str) -> str:
    return value.strip().casefold()


def phone_digits(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits


def _blank(value: str | None) -> bool:
    if value is None:
        return True
    text = value.strip()
    return text == "" or text.casefold() in {"null", "none", "n/a"}


@dataclass(frozen=True)
class AliasSet:
    user_id: str
    emails: frozenset[str]
    phones: frozenset[str]
    email_hashes: frozenset[str]
    as_of: datetime

    def intersects(self, identifiers: IdentifierBag) -> bool:
        if self.user_id in identifiers.user_ids:
            return True
        folded = {fold_email(email) for email in identifiers.emails if not _blank(email)}
        if self.emails & folded:
            return True
        phones = {phone_digits(phone) for phone in identifiers.phones if phone_digits(phone)}
        if self.phones & phones:
            return True
        hashes = {item.strip().casefold() for item in identifiers.email_hashes if not _blank(item)}
        if self.email_hashes & hashes:
            return True
        return False


@dataclass(frozen=True)
class ResolveResult:
    status: str
    user_id: str | None
    reason: str


@dataclass
class IdentityResolver:
    snapshots: list[IdentitySnapshot]
    changes: list[IdentityChange]
    links: list[IdentityLink] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._by_user = {row.user_id: row for row in self.snapshots}
        self._changes_by_user: dict[str, list[IdentityChange]] = {}
        for change in self.changes:
            self._changes_by_user.setdefault(change.user_id, []).append(change)
        for rows in self._changes_by_user.values():
            rows.sort(key=lambda item: (item.event_time, item.audit_id))
        self._email_index = self._build_email_index()

    @classmethod
    def from_dataset(cls, dataset: Dataset) -> "IdentityResolver":
        resolver = cls(snapshots=list(dataset.identities), changes=list(dataset.audit_log))
        resolver.ingest_activity(dataset.activities)
        return resolver

    def _build_email_index(self) -> dict[str, set[str]]:
        index: dict[str, set[str]] = {}

        def add(email: str, user_id: str) -> None:
            if _blank(email):
                return
            index.setdefault(fold_email(email), set()).add(user_id)

        for snapshot in self.snapshots:
            add(snapshot.email, snapshot.user_id)
        for change in self.changes:
            if change.field_name == "email":
                add(change.old_value, change.user_id)
                add(change.new_value, change.user_id)
        ambiguous = [email for email, users in index.items() if len(users) > 1]
        for email in ambiguous:
            self.warnings.append(f"email maps to multiple users ({len(index[email])} users)")
        return index

    def resolve_email(self, email: str, *, audit_at: datetime | None = None) -> ResolveResult:
        if _blank(email):
            return ResolveResult("unresolved", None, "empty email")
        users = self._email_index.get(fold_email(email), set())
        if not users:
            return ResolveResult("unresolved", None, "email not in identity snapshot or audit log")
        if len(users) > 1:
            return ResolveResult("ambiguous", None, "email is claimed by more than one user_id")
        user_id = next(iter(users))
        if audit_at is not None:
            aliases = self.aliases_at(user_id, audit_at)
            if fold_email(email) not in aliases.emails:
                return ResolveResult(
                    "unresolved",
                    None,
                    "email is associated with the user only after audit_at",
                )
        return ResolveResult("unique", user_id, "matched email")

    def aliases_at(self, user_id: str, audit_at: datetime) -> AliasSet:
        snapshot = self._by_user.get(user_id)
        if snapshot is None:
            raise KeyError(user_id)
        emails: set[str] = set()
        phones: set[str] = set()
        hashes: set[str] = set()
        changes = [row for row in self._changes_by_user.get(user_id, []) if row.event_time <= audit_at]
        future = [row for row in self._changes_by_user.get(user_id, []) if row.event_time > audit_at]

        current = {
            "email": snapshot.email,
            "phone": snapshot.phone,
            "email_hash": snapshot.email_hash,
        }
        if snapshot.updated_at > audit_at:
            # Roll the snapshot back through changes that had not happened yet.
            for change in sorted(future, key=lambda item: (item.event_time, item.audit_id), reverse=True):
                if change.field_name in current and current[change.field_name] == change.new_value:
                    current[change.field_name] = change.old_value
        if not _blank(current["email"]):
            emails.add(fold_email(current["email"]))
        if phone_digits(current["phone"]):
            phones.add(phone_digits(current["phone"]))
        if not _blank(current["email_hash"]):
            hashes.add(current["email_hash"].strip().casefold())

        for change in changes:
            if change.field_name == "email":
                if not _blank(change.old_value):
                    emails.add(fold_email(change.old_value))
                if not _blank(change.new_value):
                    emails.add(fold_email(change.new_value))
            elif change.field_name == "phone":
                if phone_digits(change.old_value):
                    phones.add(phone_digits(change.old_value))
                if phone_digits(change.new_value):
                    phones.add(phone_digits(change.new_value))
            elif change.field_name == "email_hash":
                if not _blank(change.old_value):
                    hashes.add(change.old_value.strip().casefold())
                if not _blank(change.new_value):
                    hashes.add(change.new_value.strip().casefold())
        return AliasSet(
            user_id=user_id,
            emails=frozenset(emails),
            phones=frozenset(phones),
            email_hashes=frozenset(hashes),
            as_of=audit_at,
        )

    def ingest_activity(self, activities: list[ActivityRecord]) -> None:
        for activity in activities:
            if activity.event_type != "LINK_RESOURCE_IDENTITY":
                continue
            email, user_id, sole = _parse_link_details(activity.details)
            if user_id is None:
                self.warnings.append(f"{activity.activity_id} link has no user_id")
                continue
            if email is None:
                self.warnings.append(f"{activity.activity_id} link has no email")
                continue
            resolved = self.resolve_email(email)
            if resolved.status != "unique" or resolved.user_id != user_id:
                self.warnings.append(
                    f"{activity.activity_id} link email does not agree with {user_id} ({resolved.status})"
                )
                continue
            self.links.append(
                IdentityLink(
                    evidence_id=activity.activity_id,
                    event_time=activity.event_time,
                    system_id=activity.target_system,
                    resource_id=activity.resource_id,
                    email=email,
                    user_id=user_id,
                    sole_subject=sole,
                    source="activity_link",
                )
            )

    def resources_for_user(
        self,
        user_id: str,
        audit_at: datetime,
        observations: list[Observation],
    ) -> list[tuple[str, str]]:
        aliases = self.aliases_at(user_id, audit_at)
        found: set[tuple[str, str]] = set()
        for observation in observations:
            if observation.is_claim or not observation.resource_id:
                continue
            if not observation.eligible_at(audit_at):
                continue
            if aliases.intersects(observation.identifiers):
                found.add((observation.system_id, observation.resource_id))
        for link in self.links:
            if link.user_id == user_id and link.event_time <= audit_at and link.resource_id:
                found.add((link.system_id, link.resource_id))
        return sorted(found)


def _parse_link_details(details: str) -> tuple[str | None, str | None, bool]:
    sole = SOLE_RE.search(details)
    if sole:
        return sole.group(1).rstrip(".,;"), sole.group(2), True
    linked = LINK_RE.search(details)
    if linked:
        return linked.group(1).rstrip(".,;"), linked.group(2), False
    emails = EMAIL_RE.findall(details)
    users = USER_RE.findall(details)
    if emails and users:
        return emails[0], users[0], False
    return None, None, False
