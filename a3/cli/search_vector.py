import argparse
from a3.cli.common import ROOT, DeterministicSmokeEmbedding
from a3.indexing.embeddings import BgeM3EmbeddingProvider
from a3.indexing.vector import ChromaVectorIndex
from a3.storage.sqlite_store import SQLiteEvidenceStore
def main():
    p=argparse.ArgumentParser(); p.add_argument("query"); p.add_argument("--top-k",type=int,default=5)
    p.add_argument("--index-version"); a=p.parse_args()
    with SQLiteEvidenceStore(ROOT/"data/sqlite/a3.db") as store:
        if a.index_version:
            row=store.connection.execute("SELECT manifest_json FROM index_versions WHERE index_version=?",(a.index_version,)).fetchone()
        else:
            row=store.connection.execute("SELECT manifest_json FROM index_versions ORDER BY rowid DESC LIMIT 1").fetchone()
    if not row: raise SystemExit("build the vector index first")
    import json
    manifest=json.loads(row[0]); version=manifest["index_version"]
    if manifest["embedding_provider"] == "flagembedding":
        provider=BgeM3EmbeddingProvider(manifest["embedding_model"],manifest.get("embedding_revision"))
    elif manifest["embedding_provider"] == "offline-smoke":
        provider=DeterministicSmokeEmbedding()
    else:
        raise SystemExit(f"unsupported embedding provider: {manifest['embedding_provider']}")
    index=ChromaVectorIndex(ROOT/"data/chroma",version,provider)
    for hit in index.search(a.query,a.top_k): print(hit.model_dump_json())
if __name__ == "__main__": main()
