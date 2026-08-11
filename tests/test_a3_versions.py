from a3.domain.models import Evidence
from a3.indexing.chunking import CHUNK_POLICY_VERSION, ChunkPolicy
from a3.indexing.versions import create_manifest


def manifest(text="Mock text", model="BAAI/bge-m3"):
    e = Evidence(id="M1", source_type="review", title="Mock", abstract_or_chunk=text, mock=True)
    return create_manifest(evidence=[e], chunk_policy_version=CHUNK_POLICY_VERSION,
        chunk_policy=ChunkPolicy().as_dict(), embedding_provider="flagembedding", embedding_model=model)


def test_versions_change_only_with_corpus_or_config():
    assert manifest().index_version == manifest().index_version
    assert manifest().corpus_version != manifest("Changed").corpus_version
    assert manifest().index_version != manifest(model="other").index_version
