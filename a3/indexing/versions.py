from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from a3.domain.models import Evidence, IndexManifest, canonical_hash
from a3.domain.models import (
    CHUNK_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    INDEX_MANIFEST_SCHEMA_VERSION,
    SEARCH_HIT_SCHEMA_VERSION,
    SPAN_SCHEMA_VERSION,
)


def corpus_version(evidence: Sequence[Evidence]) -> str:
    current = sorted((item.stable_id, item.content_hash) for item in evidence if not item.tombstone)
    return canonical_hash(current)


def create_manifest(*, evidence: Sequence[Evidence], chunk_policy_version: str,
                    chunk_policy: dict[str, Any], embedding_provider: str,
                    embedding_model: str, embedding_revision: str | None,
                    embedding_source_kind: str,
                    embedding_mode: str, vector_distance: str,
                    bm25_tokenizer_version: str, wiki_builder_version: str,
                    config_schema_version: str, requested_config: dict[str, Any],
                    runtime_effective_config: dict[str, Any]) -> IndexManifest:
    corpus = corpus_version(evidence)
    versions = {"manifest_schema_version": INDEX_MANIFEST_SCHEMA_VERSION,
            "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
            "chunk_schema_version": CHUNK_SCHEMA_VERSION,
            "span_schema_version": SPAN_SCHEMA_VERSION,
            "search_hit_schema_version": SEARCH_HIT_SCHEMA_VERSION,
            "config_schema_version": config_schema_version}
    base = {**versions, "corpus_version": corpus, "chunk_policy_version": chunk_policy_version,
            "chunk_policy": chunk_policy, "bm25_tokenizer_version": bm25_tokenizer_version,
            "embedding_provider": embedding_provider, "embedding_model": embedding_model,
            "embedding_revision": embedding_revision, "embedding_source_kind": embedding_source_kind,
            "embedding_mode": embedding_mode,
            "vector_distance": vector_distance, "wiki_builder_version": wiki_builder_version,
            "requested_config": requested_config, "runtime_effective_config": runtime_effective_config}
    semantic = {key: value for key, value in base.items() if key != "requested_config"}
    semantic["runtime_effective_config"] = _semantic_config(runtime_effective_config)
    return IndexManifest(**base, index_version=canonical_hash(semantic))


def _semantic_config(config: dict[str, Any]) -> dict[str, Any]:
    """Exclude storage locations while hashing every effective semantic setting."""
    copied = {key: value for key, value in config.items() if key not in {"database", "mock_fixture"}}
    for section in ("bm25", "vector", "wiki"):
        value = copied.get(section)
        if isinstance(value, dict):
            copied[section] = {key: item for key, item in value.items() if key != "root"}
    return copied
