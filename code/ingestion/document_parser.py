"""Extract text from the handover file and from ReportLab PDFs.

PDF page content in this dataset is ASCII85 plus flate, with literal text
operands. No third-party PDF library is required. Glyph-encoded scans would
be reported as partial rather than invented.
"""

from __future__ import annotations

import base64
import re
import zlib
from datetime import datetime
from pathlib import Path

from code.ingestion.normalize import (
    EMAIL_RE,
    PHONE_RE,
    RESOURCE_RE,
    USER_RE,
    bag_from_mapping,
    make_observation,
    parse_time,
)
from code.models import EvidenceFile, Observation, ParseResult

PIPE_LINE = re.compile(
    r"^-\s+(\S+)\s+\|\s+(\S+)\s+\|\s+(\S+)\s+\|\s+(\S+)\s+\|\s+(\S+)\s+\|\s+(.+)$"
)
ORDER_RE = re.compile(r"\bORD-\d+\b")
STATEMENT_RE = re.compile(r"\bNST-\d{4}-\d{4}-\d+\b")
RETAIN_RE = re.compile(
    r"retain until\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    re.IGNORECASE,
)
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_text_file(evidence: EvidenceFile, path: Path) -> ParseResult:
    text = path.read_text(encoding="utf-8")
    return _from_text(evidence, path, "text", text, text.splitlines())


def parse_pdf_file(evidence: EvidenceFile, path: Path) -> ParseResult:
    pieces = _pdf_strings(path.read_bytes())
    if not pieces:
        return ParseResult(
            file_id=evidence.file_id,
            path=str(path),
            kind="pdf",
            status="partial",
            warnings=["PDF contained no extractable literal text; contents were not inferred"],
        )
    text = "\n".join(pieces)
    result = _from_text(evidence, path, "pdf", text, pieces)
    return result


def _from_text(
    evidence: EvidenceFile,
    path: Path,
    kind: str,
    text: str,
    pieces: list[str],
) -> ParseResult:
    pipe_observations = _handover_lines(evidence, pieces if kind == "text" else text.splitlines())
    if pipe_observations:
        return ParseResult(
            file_id=evidence.file_id,
            path=str(path),
            kind=kind,
            status="parsed",
            observations=pipe_observations,
        )
    if sum(1 for piece in pieces if ORDER_RE.search(piece)) >= 2 or text.count("ORD-") >= 2:
        return ParseResult(
            file_id=evidence.file_id,
            path=str(path),
            kind=kind,
            status="parsed",
            observations=_finance_rows(evidence, pieces),
        )
    observations = _single_subject(evidence, text)
    status = "parsed" if observations else "partial"
    warnings = [] if observations else ["document text had no resource observation"]
    return ParseResult(
        file_id=evidence.file_id,
        path=str(path),
        kind=kind,
        status=status,
        observations=observations,
        warnings=warnings,
    )


def _handover_lines(evidence: EvidenceFile, lines: list[str]) -> list[Observation]:
    observations: list[Observation] = []
    for number, line in enumerate(lines, start=1):
        match = PIPE_LINE.match(line.strip())
        if not match:
            continue
        stamp, system_id, resource_id, record_type, result, subject = match.groups()
        observed_at = parse_time(stamp) or evidence.captured_at
        fields: dict[str, object] = {}
        if "@" in subject:
            fields["email"] = subject
        elif subject.startswith("user_"):
            fields["user_id"] = subject
        bag = bag_from_mapping(fields)
        presence, exposed, anonymized, redacted, flow_enabled, restore_blocked = _result_flags(
            result, record_type, bool(bag.emails or bag.phones or bag.email_hashes or bag.names)
        )
        observations.append(
            make_observation(
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
                identifiers_exposed=exposed,
                source_locator=f"{evidence.file_id}:line:{number}",
                limitations="handover line states a point-in-time check",
                confidence="high",
                result_token=result,
                anonymized=anonymized,
                redacted=redacted,
                flow_enabled=flow_enabled,
                restore_blocked=restore_blocked,
            )
        )
    return observations


def _result_flags(
    result: str,
    record_type: str,
    has_direct: bool,
) -> tuple[str, bool | None, bool | None, bool | None, bool | None, bool | None]:
    token = result.upper()
    flow_enabled = None
    restore_blocked = None
    anonymized = None
    redacted = None
    exposed: bool | None = has_direct
    if token == "NOT_FOUND":
        return "absent", None, None, None, None, None
    if token == "ANONYMIZED":
        return "present", False, True, None, None, None
    if token == "REDACTED":
        return "present", False, None, True, None, None
    if token == "IDENTIFIABLE":
        return "present", True, None, None, None, None
    if token == "DISABLED" or (token == "DISABLED" and record_type == "DATA_FLOW"):
        flow_enabled = False
    if token == "ACTIVE" and record_type == "DATA_FLOW":
        flow_enabled = True
    if token == "ACTIVE" and record_type == "BACKUP_ARCHIVE":
        restore_blocked = False
    if token == "BLOCKED":
        restore_blocked = True
    return "present", exposed, anonymized, redacted, flow_enabled, restore_blocked


def _finance_rows(evidence: EvidenceFile, pieces: list[str]) -> list[Observation]:
    observations: list[Observation] = []
    for index, piece in enumerate(pieces):
        order = ORDER_RE.search(piece)
        if not order:
            continue
        window = pieces[index : index + 14]
        blob = " ".join(window)
        users = USER_RE.findall(blob)
        retain = _retain_date(blob)
        if not users and retain is None:
            continue
        user_id = users[0] if users else None
        fields = {"user_id": user_id} if user_id else {}
        observations.append(
            make_observation(
                evidence_id=evidence.file_id,
                system_id=evidence.origin,
                resource_id=order.group(0),
                observed_at=evidence.captured_at,
                captured_at=evidence.captured_at,
                record_type="FINANCE_RETENTION_NOTE",
                replica_role="unspecified",
                replica_name=None,
                presence="present",
                identifiers=bag_from_mapping(fields),
                identifiers_exposed=False,
                source_locator=f"{evidence.file_id}:finance:{index}",
                limitations="finance retention register row; not automatically a LEGAL_HOLD_RECORD resource",
                confidence="medium",
                result_token="RETAIN_NOTE",
                retention_until=retain,
            )
        )
    return observations


def _retain_date(text: str) -> datetime | None:
    match = RETAIN_RE.search(text)
    if not match:
        return None
    parts = match.group(1).split()
    if len(parts) != 3:
        return None
    day, month_name, year = parts
    month = MONTHS.get(month_name[:3].lower())
    if month is None:
        return None
    try:
        return datetime(int(year), month, int(day), 23, 59, 59, tzinfo=parse_time("2026-01-01T00:00:00Z").tzinfo)
    except ValueError:
        return None


def _single_subject(evidence: EvidenceFile, text: str) -> list[Observation]:
    emails = list(dict.fromkeys(EMAIL_RE.findall(text)))
    users = list(dict.fromkeys(USER_RE.findall(text)))
    phones = list(dict.fromkeys(PHONE_RE.findall(text)))
    resources = list(dict.fromkeys(RESOURCE_RE.findall(text)))
    statements = list(dict.fromkeys(STATEMENT_RE.findall(text)))
    if len(emails) > 1 or len(users) > 1:
        return []
    targets = resources or statements
    if not targets:
        return []
    fields: dict[str, object] = {}
    if emails:
        fields["email"] = emails[0]
    if users:
        fields["user_id"] = users[0]
    if phones:
        fields["phone"] = phones[0]
    record_type = None
    if any(item.startswith("audit_record_") for item in targets):
        record_type = "SECURITY_AUDIT_LOG"
    elif any(item.startswith("support_") for item in targets):
        record_type = "SUPPORT_ATTACHMENT"
    elif statements:
        record_type = "CUSTOMER_STATEMENT"
    observations: list[Observation] = []
    retain = _retain_date(text)
    for resource_id in targets:
        observations.append(
            make_observation(
                evidence_id=evidence.file_id,
                system_id=_system_for_document(evidence, resource_id),
                resource_id=resource_id,
                observed_at=evidence.captured_at,
                captured_at=evidence.captured_at,
                record_type=record_type,
                replica_role="unspecified",
                replica_name=None,
                presence="present",
                identifiers=bag_from_mapping(fields),
                identifiers_exposed=bool(emails or phones),
                source_locator=f"{evidence.file_id}:text",
                limitations="identifiers co-occur in one single-subject document",
                confidence="medium",
                result_token="DOCUMENT_TEXT",
                retention_until=retain,
            )
        )
    return observations


def _system_for_document(evidence: EvidenceFile, resource_id: str) -> str:
    if resource_id.startswith("audit_record_"):
        return "security_service"
    if resource_id.startswith("support_"):
        return "support_platform"
    if evidence.origin == "legal_retention_service":
        return "legal_service"
    return evidence.origin or "unspecified"


def _pdf_strings(data: bytes) -> list[str]:
    pieces: list[str] = []
    for match in re.finditer(rb"(\d+\s+\d+\s+obj\s*<<.*?>>\s*)stream\r?\n", data, re.S):
        header = match.group(1)
        start = match.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        chunk = data[start:end].strip(b"\r\n")
        decoded = _decode_stream(header, chunk)
        if not decoded or (b"Tj" not in decoded and b"TJ" not in decoded):
            continue
        for literal in re.findall(rb"\((?:\\.|[^\\)])*\)", decoded):
            pieces.append(_pdf_unescape(literal[1:-1]).strip())
    return [piece for piece in pieces if piece]


def _decode_stream(header: bytes, chunk: bytes) -> bytes | None:
    try:
        if b"ASCII85Decode" in header and b"FlateDecode" in header:
            return zlib.decompress(base64.a85decode(chunk, adobe=True))
        if b"FlateDecode" in header and b"/Length1" not in header:
            return zlib.decompress(chunk)
    except (zlib.error, ValueError):
        return None
    return None


def _pdf_unescape(raw: bytes) -> str:
    text = raw.decode("latin1")
    text = text.replace(r"\n", "\n").replace(r"\r", "\r").replace(r"\t", "\t")
    text = text.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return text
