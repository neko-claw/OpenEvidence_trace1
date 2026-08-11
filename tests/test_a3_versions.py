from a3.domain.models import Evidence
from a3.indexing.chunking import ChunkPolicy
from a3.indexing.versions import create_manifest


def manifest(text="Mock text", model="BAAI/bge-m3"):
    evidence = Evidence(id="M1", source_type="review", title="Mock", abstract_or_chunk=text, mock=True)
    policy = ChunkPolicy(version="test-policy", max_chars=100, overlap_chars=10,
        natural_boundary_ratio=0.6)
    effective = {"chunk_policy": policy.as_dict(), "bm25": {"tokenizer_version": "tok", "root": "x"},
        "embedding": {"provider": "flagembedding", "model": model},
        "vector": {"root": "y", "distance": "cosine"},
        "wiki": {"root": "z", "builder_version": "wiki", "topics": [{"slug": "mock"}]}}
    return create_manifest(evidence=[evidence], chunk_policy_version=policy.version,
        chunk_policy=policy.as_dict(), embedding_provider="flagembedding", embedding_model=model,
        embedding_revision="rev", embedding_source_kind="test", embedding_mode="dense", vector_distance="cosine",
        bm25_tokenizer_version="tok", wiki_builder_version="wiki",
        config_schema_version="config", requested_config=effective,
        runtime_effective_config=effective)


def test_versions_change_only_with_corpus_or_semantic_config():
    assert manifest().index_version == manifest().index_version
    assert manifest().corpus_version != manifest("Changed").corpus_version
    assert manifest().index_version != manifest(model="other").index_version
