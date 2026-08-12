from __future__ import annotations

import argparse
import json
from pathlib import Path

from a3.cli.common import DEFAULT_CONFIG, DeterministicSmokeEmbedding, load_jsonl
from a3.config import ConfigLoader
from a3.indexing.bm25 import BM25Index
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from a3.indexing.embeddings import BgeM3EmbeddingProvider, EmbeddingProvider
from a3.indexing.vector import ChromaVectorIndex
from a3.indexing.versions import create_manifest
from a3.storage.sqlite_store import SQLiteEvidenceStore
from a3.wiki.builder import DeterministicOfflineWikiGenerator, build_wiki


def build(input_path: str | Path | None = None, *, real_embedding: bool = True,
          config_path: str | Path = DEFAULT_CONFIG,
          project_root: str | Path | None = None,
          provider_override: EmbeddingProvider | None = None) -> dict[str, object]:
    loaded = ConfigLoader.load(config_path, project_root=project_root)
    cfg = loaded.config
    fixture = Path(input_path) if input_path is not None else loaded.fixture_path
    imported = load_jsonl(fixture)
    if real_embedding:
        provider = provider_override or BgeM3EmbeddingProvider(cfg.embedding.model, cfg.embedding.revision,
            local_path_env=cfg.embedding.local_path_env, normalize=cfg.embedding.normalize)
        provider_name = cfg.embedding.provider
    else:
        provider = provider_override or DeterministicSmokeEmbedding()
        provider_name = "offline-smoke"
    source_kind = provider.source_kind
    policy = ChunkPolicy(version=cfg.chunk_policy.version, max_chars=cfg.chunk_policy.max_chars,
        overlap_chars=cfg.chunk_policy.overlap_chars,
        natural_boundary_ratio=cfg.chunk_policy.natural_boundary_ratio)
    requested = loaded.requested_config()
    effective = loaded.runtime_effective_config(embedding_provider=provider_name,
        embedding_model=provider.model_id, embedding_revision=provider.revision,
        embedding_source_kind=source_kind, fixture_path=fixture if input_path is not None else None)

    with SQLiteEvidenceStore(loaded.database_path) as store:
        for item in imported:
            store.insert_evidence(item)
        evidence = store.list_current_evidence()
        for item in evidence:
            chunks, spans = chunk_evidence(item, policy)
            store.replace_chunks(item, chunks, spans)
        chunks = store.list_current_chunks()
        spans = store.list_current_spans()
        manifest = create_manifest(evidence=evidence, chunk_policy_version=policy.version,
            chunk_policy=policy.as_dict(), embedding_provider=provider_name,
            embedding_model=provider.model_id, embedding_revision=provider.revision,
            embedding_source_kind=source_kind,
            embedding_mode=cfg.embedding.mode, vector_distance=cfg.vector.distance,
            bm25_tokenizer_version=cfg.bm25.tokenizer_version,
            wiki_builder_version=cfg.wiki.builder_version,
            config_schema_version=cfg.schema_version, requested_config=requested,
            runtime_effective_config=effective)
        pages, wiki_documents = build_wiki(loaded.wiki_root, evidence, spans, manifest,
            cfg.wiki.topics, DeterministicOfflineWikiGenerator(cfg.wiki.builder_version))
        bm25 = BM25Index.build(evidence, chunks, spans, manifest, wiki_documents)
        bm25.save(loaded.bm25_root)
        vector = ChromaVectorIndex(loaded.vector_root, manifest, provider)
        vector_count = vector.sync(evidence, chunks, spans)
        store.record_index(manifest)
        report: dict[str, object] = {
            "evidence_count": len(evidence), "chunk_count": len(chunks), "span_count": len(spans),
            "bm25_document_count": len(bm25.documents),
            "bm25_evidence_document_count": len(chunks),
            "bm25_wiki_navigation_document_count": len(wiki_documents),
            "vector_document_count": vector_count, "corpus_version": manifest.corpus_version,
            "index_version": manifest.index_version, "embedding_provider": manifest.embedding_provider,
            "embedding_model": manifest.embedding_model, "embedding_revision": manifest.embedding_revision,
            "embedding_source": provider.source_kind,
            "wiki_pages": [path.name for path in pages],
            "manifest": manifest.model_dump(mode="json")}
        print(json.dumps(report, indent=2, sort_keys=True))
        return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input")
    parser.add_argument("--offline-smoke", action="store_true",
        help="use the deterministic fixture embedder; never a production index")
    args = parser.parse_args()
    build(args.input, real_embedding=not args.offline_smoke, config_path=args.config)


if __name__ == "__main__":
    main()
