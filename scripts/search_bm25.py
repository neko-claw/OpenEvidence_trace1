from __future__ import annotations

import argparse

from retrieval.bm25_index import BM25Index


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Search the OpenEvidence BM25 index."
        )
    )

    parser.add_argument(
        "query",
        help="Search query",
    )

    parser.add_argument(
        "--index",
        default="data/bm25",
        help="BM25 index directory",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum number of results",
    )

    args = parser.parse_args()

    index = BM25Index.load(args.index)

    results = index.search(
        query=args.query,
        top_k=args.top_k,
    )

    print()
    print("=== BM25 Search ===")
    print("Query:", args.query)
    print("Results:", len(results))
    print()

    if not results:
        print("No matching evidence.")
        return

    for result in results:
        print(
            f"Rank {result['rank']} | "
            f"Score {result['score']:.4f}"
        )
        print(
            "Evidence ID:",
            result["evidence_id"],
        )
        print(
            "Chunk ID:",
            result["chunk_id"],
        )
        print(
            "Title:",
            result["title"],
        )
        print(
            "Source:",
            result["source_type"],
        )
        print(
            "Text:",
            result["text"],
        )
        print("-" * 60)


if __name__ == "__main__":
    main()
