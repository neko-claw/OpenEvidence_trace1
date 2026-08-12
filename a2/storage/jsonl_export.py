from __future__ import annotations

from pathlib import Path

from a2.storage.sqlite_store import SQLiteStore


def export_jsonl(store: SQLiteStore, destination: Path | str) -> int:
    """Export deterministic, UTF-8, round-trippable A2 evidence JSONL."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    records = store.list_evidence()
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(record.model_dump_json() + "\n")
    return len(records)
