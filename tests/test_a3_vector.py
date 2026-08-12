import hashlib
import math
import sys
import types
import json
from datetime import datetime, timezone

from a3.domain.models import Evidence
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from a3.indexing.embeddings import (
    DEFAULT_BGE_M3_MODEL_ID,
    BgeM3EmbeddingProvider,
    resolve_bge_m3_source,
)
from a3.indexing.vector import ChromaVectorIndex
from tests.a3_support import make_manifest


class FakeEmbeddingProvider:
    model_id = "fake-v1"
    revision = "test"
    source_kind = "test-fixture"

    @staticmethod
    def _one(text):
        # Deterministic, normalized feature hashing; no network/model import.
        vec = [0.0] * 16
        for token in text.casefold().replace(":", " ").split():
            vec[int(hashlib.sha256(token.encode()).hexdigest(), 16) % len(vec)] += 1
        norm = math.sqrt(sum(x*x for x in vec)) or 1
        return [x/norm for x in vec]

    def encode_documents(self, texts): return [self._one(x) for x in texts]
    def encode_queries(self, texts): return [self._one(x) for x in texts]


POLICY = ChunkPolicy(version="test", max_chars=1200, overlap_chars=150, natural_boundary_ratio=.6)


def test_bge_provider_is_pinned_normalized_and_dense_only(monkeypatch):
    calls = {}

    class Dense:
        def tolist(self): return [[1.0, 0.0]]

    class FakeModel:
        def __init__(self, model_id, **kwargs): calls["init"] = (model_id, kwargs)
        def encode(self, texts, **kwargs):
            calls["encode"] = (texts, kwargs)
            return {"dense_vecs": Dense()}

    monkeypatch.setitem(sys.modules, "FlagEmbedding", types.SimpleNamespace(BGEM3FlagModel=FakeModel))
    provider = BgeM3EmbeddingProvider()
    assert provider.encode_queries(["fixture"]) == [[1.0, 0.0]]
    assert calls["init"][1]["normalize_embeddings"] is True
    assert calls["init"][1]["revision"] == provider.revision
    assert calls["encode"][1] == {"return_dense": True, "return_sparse": False, "return_colbert_vecs": False}


def test_bge_local_source_resolution(monkeypatch, tmp_path):
    monkeypatch.delenv("A3_BGE_M3_MODEL_PATH", raising=False)
    assert resolve_bge_m3_source() == DEFAULT_BGE_M3_MODEL_ID

    missing = tmp_path / "missing"
    monkeypatch.setenv("A3_BGE_M3_MODEL_PATH", str(missing))
    try:
        resolve_bge_m3_source()
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing local model path was accepted")

    incomplete = tmp_path / "incomplete"; incomplete.mkdir()
    monkeypatch.setenv("A3_BGE_M3_MODEL_PATH", str(incomplete))
    try:
        resolve_bge_m3_source()
    except RuntimeError:
        pass
    else:
        raise AssertionError("incomplete local model path was accepted")

    complete = tmp_path / "complete"; complete.mkdir()
    for name in ("config.json", "pytorch_model.bin", "tokenizer_config.json"):
        (complete / name).write_text("fixture", encoding="utf-8")
    monkeypatch.setenv("A3_BGE_M3_MODEL_PATH", str(complete))
    assert resolve_bge_m3_source() == str(complete.resolve())


def test_local_source_does_not_change_logical_model_id(monkeypatch, tmp_path):
    complete = tmp_path / "model"; complete.mkdir()
    for name in ("config.json", "pytorch_model.bin", "tokenizer_config.json"):
        (complete / name).write_text("fixture", encoding="utf-8")
    monkeypatch.setenv("A3_BGE_M3_MODEL_PATH", str(complete))

    calls = {}
    class FakeModel:
        def __init__(self, source, **kwargs): calls.update(source=source, kwargs=kwargs)
    monkeypatch.setitem(sys.modules, "FlagEmbedding", types.SimpleNamespace(BGEM3FlagModel=FakeModel))
    provider = BgeM3EmbeddingProvider()
    assert provider.model_id == DEFAULT_BGE_M3_MODEL_ID
    assert provider.source_kind == "local"
    assert calls["source"] == str(complete.resolve())
    assert "revision" not in calls["kwargs"]


def test_local_source_accepts_complete_safetensors_shards(monkeypatch, tmp_path):
    complete = tmp_path / "sharded"; complete.mkdir()
    for name in ("config.json", "tokenizer_config.json", "model-00001-of-00002.safetensors",
                 "model-00002-of-00002.safetensors"):
        (complete / name).write_text("fixture", encoding="utf-8")
    (complete / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {
        "a": "model-00001-of-00002.safetensors", "b": "model-00002-of-00002.safetensors"}}),
        encoding="utf-8")
    monkeypatch.setenv("A3_BGE_M3_MODEL_PATH", str(complete))
    assert resolve_bge_m3_source() == str(complete.resolve())


def test_vector_explicit_embeddings_idempotence_persistence_and_metadata(tmp_path):
    evidence = [Evidence(id="M1", source_type="review", title="Pressure mock",
        abstract_or_chunk="pressure pressure synthetic", published_at=datetime(2024,1,1,tzinfo=timezone.utc), mock=True),
        Evidence(id="M2", source_type="trial", title="Lipids mock",
        abstract_or_chunk="lipids cholesterol synthetic", published_at=datetime(2026,1,1,tzinfo=timezone.utc), mock=True)]
    chunked = [chunk_evidence(item, POLICY) for item in evidence]
    chunks = sum((item[0] for item in chunked), [])
    spans = sum((item[1] for item in chunked), [])
    manifest = make_manifest(evidence, provider="flagembedding", model="fake-v1",
        revision="test", source_kind="test-fixture")
    root = tmp_path / "chroma"
    index = ChromaVectorIndex(root, manifest, FakeEmbeddingProvider())
    assert index.sync(evidence, chunks, spans) == 2
    assert index.sync(evidence, chunks, spans) == 2
    hit = index.search("cholesterol", 9)[0]
    assert hit.evidence_id == "M2" and hit.distance is not None
    reopened = ChromaVectorIndex(root, manifest, FakeEmbeddingProvider())
    assert reopened.collection.count() == 2
    assert all(value is not None for value in hit.metadata.values())
    dated = reopened.search("synthetic", 5, {"date_to":"2024-12-31"})
    assert [item.evidence_id for item in dated] == ["M1"]
    current_chunks = [chunk for chunk in chunks if chunk.evidence_id == "M1"]
    current_spans = [span for span in spans if span.chunk_id in {chunk.chunk_id for chunk in current_chunks}]
    assert reopened.sync([evidence[0]], current_chunks, current_spans) == 1
    assert all(hit.evidence_id != "M2" for hit in reopened.search("cholesterol", 5))
