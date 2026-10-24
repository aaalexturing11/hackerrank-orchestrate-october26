"""Turn the checked screenshot facts into observations.

The facts live in image_facts.py so a packaged run does not need to view pixels.
Files with no checked facts stay requires_processing and produce no guesses.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from code.ingestion.image_facts import IMAGE_FACTS
from code.ingestion.normalize import make_observation
from code.models import EvidenceFile, Observation, ParseResult


def image_extraction_available() -> bool:
    return True


def parse_image_file(evidence: EvidenceFile, path: Path) -> ParseResult:
    facts = IMAGE_FACTS.get(evidence.file_id)
    if not facts:
        return ParseResult(
            file_id=evidence.file_id,
            path=str(path),
            kind="image",
            status="requires_processing",
            warnings=["no checked extraction is stored for this screenshot"],
        )
    observations = [_observation(evidence, index, fact) for index, fact in enumerate(facts)]
    return ParseResult(
        file_id=evidence.file_id,
        path=str(path),
        kind="image",
        status="parsed",
        observations=observations,
    )


def _observation(evidence: EvidenceFile, index: int, fact: dict[str, object]) -> Observation:
    from code.models import IdentifierBag

    bag = IdentifierBag(
        emails=tuple(fact.get("emails") or ()),
        phones=tuple(fact.get("phones") or ()),
        user_ids=tuple(fact.get("user_ids") or ()),
        names=tuple(fact.get("names") or ()),
    )
    observed = fact.get("observed_at")
    return make_observation(
        evidence_id=evidence.file_id,
        system_id=str(fact["system_id"]),
        resource_id=str(fact["resource_id"]),
        observed_at=observed if isinstance(observed, datetime) else evidence.captured_at,
        captured_at=evidence.captured_at,
        record_type=str(fact["record_type"]) if fact.get("record_type") else None,
        replica_role="unspecified",
        replica_name=None,
        presence=str(fact["presence"]),
        identifiers=bag,
        identifiers_exposed=fact.get("identifiers_exposed") if isinstance(fact.get("identifiers_exposed"), bool) else None,
        source_locator=f"{evidence.file_id}:image:{index}",
        limitations=str(fact.get("limitations") or "screenshot"),
        confidence="high",
        result_token="SCREENSHOT",
        anonymized=fact.get("anonymized") if isinstance(fact.get("anonymized"), bool) else None,
        flow_enabled=fact.get("flow_enabled") if isinstance(fact.get("flow_enabled"), bool) else None,
        restore_blocked=fact.get("restore_blocked") if isinstance(fact.get("restore_blocked"), bool) else None,
        retention_until=fact.get("retention_until") if isinstance(fact.get("retention_until"), datetime) else None,
        shared_context=fact.get("shared_context") if isinstance(fact.get("shared_context"), bool) else None,
    )
