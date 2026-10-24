"""Dispatch each manifest file to one parser and keep failures visible."""

from __future__ import annotations

import logging
from pathlib import Path

from code.ingestion.csv_loader import Dataset
from code.ingestion.document_parser import parse_pdf_file, parse_text_file
from code.ingestion.image_parser import parse_image_file
from code.ingestion.json_parser import parse_json_file
from code.ingestion.log_parser import parse_log_file
from code.ingestion.sql_parser import parse_sql_file
from code.models import Observation, ParseResult

LOGGER = logging.getLogger(__name__)


class EvidenceRegistry:
    def __init__(self, dataset: Dataset, dataset_root: Path) -> None:
        self.dataset = dataset
        self.dataset_root = dataset_root

    def parse_all(self) -> list[ParseResult]:
        results: list[ParseResult] = []
        for evidence in self.dataset.evidence:
            result = self.parse_one(evidence.file_id)
            results.append(result)
            LOGGER.info(
                "evidence %s status=%s observations=%s warnings=%s",
                result.file_id,
                result.status,
                len(result.observations),
                len(result.warnings),
            )
        return results

    def parse_one(self, file_id: str) -> ParseResult:
        evidence = self.dataset.evidence_by_id[file_id]
        path = self.dataset_root / evidence.file_path
        if not path.is_file():
            return ParseResult(
                file_id=file_id,
                path=str(path),
                kind=path.suffix.lower().lstrip(".") or "missing",
                status="failed",
                warnings=["file missing on disk"],
            )
        suffix = path.suffix.lower()
        try:
            if suffix == ".sql":
                return parse_sql_file(evidence, path)
            if suffix == ".json":
                return parse_json_file(evidence, path)
            if suffix == ".log":
                return parse_log_file(evidence, path)
            if suffix == ".txt":
                return parse_text_file(evidence, path)
            if suffix == ".pdf":
                return parse_pdf_file(evidence, path)
            if suffix == ".png":
                return parse_image_file(evidence, path)
            return ParseResult(
                file_id=file_id,
                path=str(path),
                kind=suffix.lstrip(".") or "unknown",
                status="unsupported",
                warnings=[f"no parser for {suffix or 'extensionless file'}"],
            )
        except Exception as exc:
            LOGGER.exception("parser failed for %s", file_id)
            return ParseResult(
                file_id=file_id,
                path=str(path),
                kind=suffix.lstrip("."),
                status="failed",
                warnings=[f"{type(exc).__name__}: {exc}"],
            )


def observations_from(results: list[ParseResult]) -> list[Observation]:
    rows: list[Observation] = []
    for result in results:
        rows.extend(result.observations)
    return rows
