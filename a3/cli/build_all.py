from __future__ import annotations

import argparse
import json

from a3.cli.common import DB, FIXTURE, ROOT, DeterministicSmokeEmbedding, load_jsonl
from a3.indexing.bm25 import BM25Index
from a3.indexing.chunking import CHUNK_POLICY_VERSION, ChunkPolicy, chunk_evidence
from a3.indexing.embeddings import BgeM3EmbeddingProvider
from a3.indexing.vector import ChromaVectorIndex
from a3.indexing.versions import create_manifest
from a3.storage.sqlite_store import SQLiteEvidenceStore
from a3.wiki.builder import build_wiki


def build(input_path=FIXTURE, *, real_embedding=True):
    imported = load_jsonl(input_path)
    provider = BgeM3EmbeddingProvider() if real_embedding else DeterministicSmokeEmbedding()
    with SQLiteEvidenceStore(DB) as store:
        for item in imported:
            store.insert_evidence(item)
        evidence = store.list_current_evidence()
        policy = ChunkPolicy()
        for item in evidence:
            chunks, spans = chunk_evidence(item, policy)
            store.replace_chunks(item, chunks, spans)
        chunks = store.list_current_chunks(); spans = store.list_current_spans()
        manifest = create_manifest(evidence=evidence, chunk_policy_version=CHUNK_POLICY_VERSION,
            chunk_policy=policy.as_dict(), embedding_provider="flagembedding" if real_embedding else "offline-smoke",
            embedding_model=provider.model_id, embedding_revision=provider.revision)
        bm25 = BM25Index.build(evidence, chunks, manifest.index_version)
        bm25.save(ROOT / "data/bm25")
        vector = ChromaVectorIndex(ROOT / "data/chroma", manifest.index_version, provider)
        vector_count = vector.sync(evidence, chunks)
        store.record_index(manifest)
        pages = build_wiki(ROOT / "wiki", evidence, spans, manifest)
        report = {"evidence_count": len(evidence), "chunk_count": len(chunks), "span_count": len(spans),
            "bm25_document_count": len(bm25.documents), "vector_document_count": vector_count,
            "corpus_version": manifest.corpus_version, "index_version": manifest.index_version,
            "embedding_provider": manifest.embedding_provider, "embedding_model": manifest.embedding_model,
            "embedding_revision": manifest.embedding_revision,
            "embedding_source": getattr(provider, "source_kind", "offline-fixture"),
            "wiki_pages": [p.name for p in pages]}
        print(json.dumps(report, indent=2, sort_keys=True)); return report


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--input", default=str(FIXTURE))
    parser.add_argument("--offline-smoke", action="store_true",
        help="use the deterministic fixture embedder; never a production index")
    args = parser.parse_args()
    build(args.input, real_embedding=not args.offline_smoke)


if __name__ == "__main__": main()
