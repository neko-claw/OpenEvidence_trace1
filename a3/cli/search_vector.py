import argparse
import json

from a3.cli.common import DEFAULT_CONFIG, DeterministicSmokeEmbedding
from a3.config import ConfigLoader
from a3.domain.models import IndexManifest
from a3.indexing.embeddings import BgeM3EmbeddingProvider
from a3.indexing.vector import ChromaVectorIndex
from a3.storage.sqlite_store import SQLiteEvidenceStore


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("query"); parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--index-version"); parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(); loaded = ConfigLoader.load(args.config)
    with SQLiteEvidenceStore(loaded.database_path) as store:
        if args.index_version:
            row = store.connection.execute("SELECT manifest_json FROM index_versions WHERE index_version=?",
                (args.index_version,)).fetchone()
        else:
            row = store.connection.execute("SELECT manifest_json FROM index_versions ORDER BY rowid DESC LIMIT 1").fetchone()
    if not row: raise SystemExit("build the vector index first")
    manifest = IndexManifest.model_validate(json.loads(row[0]))
    if manifest.embedding_provider == "flagembedding":
        cfg = loaded.config.embedding
        provider = BgeM3EmbeddingProvider(manifest.embedding_model, manifest.embedding_revision,
            local_path_env=cfg.local_path_env, normalize=cfg.normalize)
    elif manifest.embedding_provider == "offline-smoke":
        provider = DeterministicSmokeEmbedding()
    else:
        raise SystemExit(f"unsupported embedding provider: {manifest.embedding_provider}")
    index = ChromaVectorIndex(loaded.vector_root, manifest, provider)
    for hit in index.search(args.query, args.top_k): print(hit.model_dump_json())


if __name__ == "__main__": main()
