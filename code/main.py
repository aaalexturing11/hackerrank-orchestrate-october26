"""Foundation entry point.

Loads the dataset and parses evidence. It does not write root output.csv and
does not assign deletion statuses.
"""

from __future__ import annotations

import logging
import sys
from collections import Counter

from code.config import dataset_dir, repo_root
from code.ingestion.csv_loader import load_dataset
from code.ingestion.evidence_registry import EvidenceRegistry


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    if str(repo_root()) not in sys.path:
        sys.path.insert(0, str(repo_root()))
    dataset = load_dataset()
    print(f"requests={len(dataset.requests)}")
    print(f"identities={len(dataset.identities)}")
    print(f"audit_log={len(dataset.audit_log)}")
    print(f"activities={len(dataset.activities)}")
    print(f"rules={len(dataset.rules)}")
    print(f"evidence_files={len(dataset.evidence)}")
    print(f"dataset_warnings={len(dataset.warnings)}")
    registry = EvidenceRegistry(dataset, dataset_dir())
    results = registry.parse_all()
    counts = Counter(result.status for result in results)
    observations = sum(len(result.observations) for result in results)
    print(f"parse_status={dict(counts)}")
    print(f"observations={observations}")
    pending = [result.file_id for result in results if result.status == "requires_processing"]
    failed = [result.file_id for result in results if result.status == "failed"]
    partial = [result.file_id for result in results if result.status in {"partial", "unsupported"}]
    print(f"images_requiring_processing={','.join(pending)}")
    print(f"failed={','.join(failed)}")
    print(f"partial_or_unsupported={','.join(partial)}")
    print("output_csv_written=false")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
