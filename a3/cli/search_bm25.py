import argparse

from a3.cli.common import DEFAULT_CONFIG
from a3.config import ConfigLoader
from a3.indexing.bm25 import BM25Index


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5); parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(); root = ConfigLoader.load(args.config).bm25_root
    paths = sorted(root.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not paths: raise SystemExit("build BM25 first")
    for hit in BM25Index.load(paths[0].parent).search(args.query, args.top_k): print(hit.model_dump_json())


if __name__ == "__main__": main()
