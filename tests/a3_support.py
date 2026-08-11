from collections.abc import Sequence

from a3.domain.models import Evidence, IndexManifest
from a3.indexing.chunking import ChunkPolicy
from a3.indexing.versions import create_manifest

POLICY = ChunkPolicy(version="test-policy", max_chars=1200, overlap_chars=150,
                     natural_boundary_ratio=0.6)


def make_manifest(evidence: Sequence[Evidence], *, provider: str = "offline-smoke",
                  model: str = "test-smoke", revision: str | None = "fixture",
                  source_kind: str = "offline-fixture") -> IndexManifest:
    runtime = {"database": "db", "mock_fixture": "fixture", "chunk_policy": POLICY.as_dict(),
        "bm25": {"root": "bm25", "tokenizer_version": "test-tokenizer"},
        "embedding": {"provider": provider, "model": model, "revision": revision,
                      "source_kind": source_kind, "mode": "dense"},
        "vector": {"root": "vector", "distance": "cosine"},
        "wiki": {"root": "wiki", "builder_version": "test-wiki", "topics": []}}
    return create_manifest(evidence=evidence, chunk_policy_version=POLICY.version,
        chunk_policy=POLICY.as_dict(), embedding_provider=provider, embedding_model=model,
        embedding_revision=revision, embedding_source_kind=source_kind,
        embedding_mode="dense", vector_distance="cosine",
        bm25_tokenizer_version="test-tokenizer", wiki_builder_version="test-wiki",
        config_schema_version="test-config", requested_config=runtime,
        runtime_effective_config=runtime)
