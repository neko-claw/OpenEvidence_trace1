import argparse
from pathlib import Path
from a3.cli.common import ROOT
from a3.indexing.bm25 import BM25Index
def main():
    p=argparse.ArgumentParser(); p.add_argument("query"); p.add_argument("--top-k", type=int, default=5); a=p.parse_args()
    paths=sorted((ROOT/"data/bm25").glob("*/manifest.json"), key=lambda x:x.stat().st_mtime, reverse=True)
    if not paths: raise SystemExit("build BM25 first")
    for hit in BM25Index.load(paths[0].parent).search(a.query,a.top_k): print(hit.model_dump_json())
if __name__ == "__main__": main()
