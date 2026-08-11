from __future__ import annotations

import argparse

from core.models import Evidence
from retrieval.chunking import (
    ChunkPolicy,
    chunk_evidence,
)
from storage.database import EvidenceDatabase


def build_chunks(
    db_path: str,
    policy: ChunkPolicy,
) -> dict:
    """
    从 SQLite 最新 Evidence 构建 Chunk。

    重复运行不会重复插入相同 chunk。
    """

    report = {
        "evidence_processed": 0,
        "evidence_without_text": 0,
        "chunks_generated": 0,
        "chunks_inserted": 0,
        "chunks_existing": 0,
    }

    with EvidenceDatabase(db_path) as db:
        db.init_schema()

        records = db.list_latest_evidence()

        for record in records:
            evidence = Evidence.model_validate(
                record
            )

            report[
                "evidence_processed"
            ] += 1

            chunks = chunk_evidence(
                evidence,
                policy,
            )

            if not chunks:
                report[
                    "evidence_without_text"
                ] += 1

                continue

            for chunk in chunks:
                report[
                    "chunks_generated"
                ] += 1

                inserted = db.insert_chunk(
                    chunk=chunk,
                    evidence_content_hash=(
                        evidence.content_hash
                    ),
                )

                if inserted:
                    report[
                        "chunks_inserted"
                    ] += 1
                else:
                    report[
                        "chunks_existing"
                    ] += 1

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic Evidence chunks "
            "for OpenEvidence A3."
        )
    )

    parser.add_argument(
        "--db",
        default="data/sqlite/openevidence.db",
    )

    parser.add_argument(
        "--max-chars",
        type=int,
        default=800,
    )

    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=120,
    )

    args = parser.parse_args()

    policy = ChunkPolicy(
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
    )

    report = build_chunks(
        db_path=args.db,
        policy=policy,
    )

    print()
    print("=== Chunk Build Report ===")
    print(
        "Evidence processed:",
        report["evidence_processed"],
    )
    print(
        "Evidence without text:",
        report["evidence_without_text"],
    )
    print(
        "Chunks generated:",
        report["chunks_generated"],
    )
    print(
        "Chunks inserted:",
        report["chunks_inserted"],
    )
    print(
        "Chunks existing:",
        report["chunks_existing"],
    )
    print("==========================")


if __name__ == "__main__":
    main()
