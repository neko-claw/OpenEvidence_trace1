from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from a3.domain.models import Evidence, IndexManifest, canonical_hash

BM25_TOKENIZER_VERSION = "a3-bm25-tokenizer-v0.1"
WIKI_BUILDER_VERSION = "a3-wiki-v0.1"


def corpus_version(evidence: Sequence[Evidence]) -> str:
    current = sorted((item.stable_id, item.content_hash) for item in evidence if not item.tombstone)
    return canonical_hash(current)


def create_manifest(*, evidence: Sequence[Evidence], chunk_policy_version: str,
                    chunk_policy: dict[str, Any], embedding_provider: str,
                    embedding_model: str, embedding_revision: str | None = None) -> IndexManifest:
    corpus = corpus_version(evidence)
    base = {"corpus_version": corpus, "chunk_policy_version": chunk_policy_version,
            "chunk_policy": chunk_policy, "bm25_tokenizer_version": BM25_TOKENIZER_VERSION,
            "embedding_provider": embedding_provider, "embedding_model": embedding_model,
            "embedding_revision": embedding_revision, "embedding_mode": "dense",
            "vector_distance": "cosine", "wiki_builder_version": WIKI_BUILDER_VERSION}
    return IndexManifest(**base, index_version=canonical_hash(base))
