from datetime import datetime, timezone

import pytest

from a3.domain.models import Evidence
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from a5.adapters.a3 import A3AdapterError, adapt_a3_selection
from tests.a3_support import make_manifest

POLICY = ChunkPolicy(version="test", max_chars=24, overlap_chars=4, natural_boundary_ratio=.5)


def mock_evidence(**updates):
    data = dict(id="M1", source_type="trial", title="Mock",
        abstract_or_chunk="First synthetic sentence. Second synthetic sentence.",
        page="S12", population="synthetic adults", mock=True,
        provenance={"fixture": "v1"})
    data.update(updates)
    return Evidence(**data)


def adapt(evidence, chunks=None, spans=None, **kwargs):
    generated_chunks, generated_spans = chunk_evidence(evidence, POLICY)
    chunks = generated_chunks if chunks is None else chunks
    spans = generated_spans if spans is None else spans
    manifest = kwargs.pop("manifest", make_manifest([evidence]))
    return adapt_a3_selection(evidence, chunks, spans, manifest,
        index_version=kwargs.pop("index_version", manifest.index_version),
        corpus_version=kwargs.pop("corpus_version", manifest.corpus_version), **kwargs)


def test_canonical_adapter_preserves_per_span_locator_and_all_versions():
    evidence = mock_evidence()
    chunks, spans = chunk_evidence(evidence, POLICY)
    chunks[1] = chunks[1].model_copy(update={"raw_page": "appendix-A"})
    spans = [span.model_copy(update={"raw_page": "appendix-A"}) if span.chunk_id == chunks[1].chunk_id else span
             for span in spans]
    result = adapt(evidence, chunks, spans)
    record = result.evidence
    provenance = record.source_metadata["span_provenance"]
    assert record.retrieval_score is None and record.mock
    assert record.content == "\n".join(chunk.text for chunk in chunks)
    assert {item["raw_page"] for item in provenance.values()} == {"S12", "appendix-A"}
    assert all({"char_start", "document_char_start", "span_content_hash",
                "chunk_content_hash", "evidence_content_hash"} <= set(item)
               for item in provenance.values())
    assert result.diagnostics.selected_chunk_ids == [chunk.chunk_id for chunk in chunks]
    assert result.diagnostics.selected_span_ids == [span.span_id for span in spans]
    assert result.diagnostics.runtime_config_hash


@pytest.mark.parametrize(("mutate", "reason"), [
    (lambda e, c, s, m: (e, [c[0].model_copy(update={"evidence_id": "OTHER"})], s, m, {}), "stale_chunk"),
    (lambda e, c, s, m: (e, [c[0].model_copy(update={"evidence_content_hash": "stale"})], s, m, {}), "evidence_hash_mismatch"),
    (lambda e, c, s, m: (e, [c[0].model_copy(update={"content_hash": "stale"})], s, m, {}), "chunk_hash_mismatch"),
    (lambda e, c, s, m: (e, c, [s[0].model_copy(update={"text": "stale"})], m, {}), "stale_span"),
    (lambda e, c, s, m: (e, c[:1], s, m, {"selected_span_ids": [s[-1].span_id]}), "span_not_selected"),
    (lambda e, c, s, m: (e, c, s, m, {"index_version": "wrong"}), "index_version_mismatch"),
    (lambda e, c, s, m: (e, c, s, m, {"corpus_version": "wrong"}), "corpus_version_mismatch"),
])
def test_adapter_rejects_stale_or_mismatched_selection(mutate, reason):
    evidence = mock_evidence(); chunks, spans = chunk_evidence(evidence, POLICY)
    manifest = make_manifest([evidence])
    evidence, chunks, spans, manifest, overrides = mutate(evidence, chunks, spans, manifest)
    args = {"index_version": manifest.index_version, "corpus_version": manifest.corpus_version, **overrides}
    with pytest.raises(A3AdapterError) as caught:
        adapt_a3_selection(evidence, chunks, spans, manifest, **args)
    assert reason in caught.value.reason_codes


def test_adapter_rejects_tombstone_missing_production_and_mock_provenance():
    tombstone = mock_evidence(tombstone=True)
    with pytest.raises(A3AdapterError) as caught:
        adapt(tombstone)
    assert "tombstoned_evidence" in caught.value.reason_codes

    real = Evidence(id="R1", source_type="trial", title="Real-shaped",
        abstract_or_chunk="No provenance supplied.")
    with pytest.raises(A3AdapterError) as caught:
        adapt(real)
    assert "missing_provenance" in caught.value.reason_codes

    invalid_mock = Evidence.model_construct(id="M2", source_type="trial", title="Mock",
        abstract_or_chunk="Mock.", authors=[], published_at=None, url=None,
        pmid=None, doi=None, nct_id=None, guideline_name=None, upstream_id="M2", page=None,
        section=None, evidence_level=None, population=None, intervention=None, comparator=None,
        outcome=None, fetched_at=datetime.now(timezone.utc), provenance={}, mock=True, tombstone=False)
    with pytest.raises(A3AdapterError) as caught:
        adapt(invalid_mock)
    assert "mock_provenance_violation" in caught.value.reason_codes
