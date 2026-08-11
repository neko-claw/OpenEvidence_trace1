from __future__ import annotations

import argparse

from retrieval.bm25_index import BM25Index
from storage.database import EvidenceDatabase


def build_bm25(
    db_path: str,
    output_dir: str,
) -> dict:
    """
    从 SQLite 当前有效 Chunk 构建 BM25 索引。
    """

    with EvidenceDatabase(db_path) as db:
        db.init_schema()
        chunks = db.list_current_chunks()

    index = BM25Index.from_chunks(chunks)

    index.save(output_dir)

    return {
        "document_count": len(chunks),
        "output_dir": output_dir,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build BM25 index from current "
            "OpenEvidence chunks."
        )
    )

    parser.add_argument(
        "--db",
        default="data/sqlite/openevidence.db",
        help="SQLite database path",
    )

    parser.add_argument(
        "--output",
        default="data/bm25",
        help="BM25 index output directory",
    )

    args = parser.parse_args()

    report = build_bm25(
        db_path=args.db,
        output_dir=args.output,
    )

    print()
    print("=== BM25 Build Report ===")
    print(
        "Documents:",
        report["document_count"],
    )
    print(
        "Output:",
        report["output_dir"],
    )
    print("=========================")


if __name__ == "__main__":
    main()
