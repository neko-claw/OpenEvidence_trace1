from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


SPLITS = ("DEV", "TEST", "STRESS", "EXTERNAL", "RESERVE")


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def canonical_split_hash(records: Iterable[dict[str, Any]]) -> str:
    canonical = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for record in records
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def split_hashes(records: list[dict[str, Any]]) -> dict[str, str]:
    return {
        split: canonical_split_hash(record for record in records if record["split"] == split)
        for split in SPLITS
    }


def source_group_audit(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(record["source_group_id"] for record in records)
    group_splits: dict[str, set[str]] = {}
    for record in records:
        group_splits.setdefault(record["source_group_id"], set()).add(record["split"])
    return {
        "total_groups": len(counts),
        "singleton_groups": sum(count == 1 for count in counts.values()),
        "cross_split_collisions": sum(len(splits) > 1 for splits in group_splits.values()),
    }
