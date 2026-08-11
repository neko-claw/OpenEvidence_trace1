import hashlib
import math

from a3.domain.models import Evidence
from a3.indexing.bm25 import BM25Index
from a3.indexing.chunking import chunk_evidence
from a3.indexing.vector import ChromaVectorIndex
from tests.a3_support import POLICY, make_manifest


class FakeEmbedding:
    model_id = "fake-search"
    revision = "test"
    source_kind = "test-fixture"

    @staticmethod
    def _encode(text):
        values = [0.0] * 8
        for token in text.casefold().split():
            values[int(hashlib.sha256(token.encode()).hexdigest(), 16) % len(values)] += 1
        norm = math.sqrt(sum(value * value for value in values)) or 1
        return [value / norm for value in values]

    def encode_documents(self, texts): return [self._encode(text) for text in texts]
    def encode_queries(self, texts): return [self._encode(text) for text in texts]


def test_bm25_and_vector_preserve_the_same_typed_provenance(tmp_path):
    evidence = [Evidence(id="MOCK-S1", source_type="review", title="Pressure fixture",
        abstract_or_chunk="pressure exact synthetic sentence.", mock=True,
        provenance={"fixture": "search-contract"})]
    chunks, spans = chunk_evidence(evidence[0], POLICY)
    manifest = make_manifest(evidence, provider="flagembedding", model="fake-search",
        revision="test", source_kind="test-fixture")
    lexical = BM25Index.build(evidence, chunks, spans, manifest).search("pressure", 1)[0]
    vector_index = ChromaVectorIndex(tmp_path / "chroma", manifest, FakeEmbedding())
    vector_index.sync(evidence, chunks, spans)
    vector = vector_index.search("pressure", 1)[0]
    fields = ("document_kind", "evidence_id", "mock", "tombstone", "live_state",
        "chunk_content_hash", "evidence_content_hash", "corpus_version", "index_version",
        "chunk_policy_version", "bm25_tokenizer_version", "embedding_provider",
        "embedding_model", "embedding_revision", "embedding_source_kind",
        "wiki_builder_version", "config_schema_version", "raw_page", "section")
    assert {field: getattr(lexical, field) for field in fields} == {
        field: getattr(vector, field) for field in fields}
    assert [item.model_dump() for item in lexical.span_refs] == [item.model_dump() for item in vector.span_refs]
