from a3.domain.models import Evidence
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from a5.adapters.a3_evidence_adapter import adapt_a3_evidence


def test_adapter_maps_exact_content_pico_provenance_and_non_numeric_page():
    evidence = Evidence(id="M1", source_type="trial", title="Mock", abstract_or_chunk="Exact synthetic claim.",
        page="S12", population="synthetic adults", mock=True, provenance={"fixture":"v1"})
    policy = ChunkPolicy(version="test", max_chars=1200, overlap_chars=150, natural_boundary_ratio=.6)
    chunks, spans = chunk_evidence(evidence, policy)
    record = adapt_a3_evidence(evidence, chunks, spans, index_version="i", corpus_version="c")
    assert record.content == chunks[0].text and record.population == "synthetic adults"
    assert record.retrieval_score is None and record.spans[0].text == spans[0].text
    assert record.spans[0].page is None and record.source_metadata["raw_page"] == "S12"
