"""Score the public sample against itself and print the foundation fixture notes.

Run from the repository root:

    python -m code.evaluation.main
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from code.config import repo_root
from code.evaluation.score import format_report, score_rows


def load_sample_output(path: Path | None = None) -> list[dict[str, str]]:
    sample = path or (repo_root() / "dataset" / "sample_output.csv")
    with sample.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def score_sample_against_itself() -> object:
    rows = load_sample_output()
    return score_rows(rows, rows)


def main() -> int:
    if str(repo_root()) not in sys.path:
        sys.path.insert(0, str(repo_root()))
    report = score_sample_against_itself()
    print(format_report(report))
    perfect = (
        report.failures == []
        and report.field_mismatches == []
        and report.status_correct == report.cases
        and report.exact_rows == report.cases
        and report.sequence_exact == report.cases
        and report.field_matches == report.field_total
    )
    print(f"self_comparison_perfect={perfect}")
    return 0 if perfect else 1


if __name__ == "__main__":
    raise SystemExit(main())
