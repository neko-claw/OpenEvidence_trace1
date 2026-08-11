from a3.domain.models import Evidence
from a3.indexing.chunking import ChunkPolicy, chunk_evidence


def test_chunks_and_spans_are_deterministic_exact_and_retain_locator():
    evidence = Evidence(id="MOCK-E1", source_type="trial", title="Mock",
        abstract_or_chunk="First synthetic sentence. 第二个合成句子。 Third synthetic sentence.",
        page="S12", section="mock methods", mock=True)
    policy = ChunkPolicy(max_chars=40, overlap_chars=5, natural_boundary_ratio=.5)
    chunks1, spans1 = chunk_evidence(evidence, policy)
    chunks2, spans2 = chunk_evidence(evidence, policy)
    assert [c.chunk_id for c in chunks1] == [c.chunk_id for c in chunks2]
    assert len(chunks1) > 1
    assert chunks1[0].page == "S12"
    assert [s.span_id for s in spans1] == [s.span_id for s in spans2]
    by_chunk = {c.chunk_id: c for c in chunks1}
    for span in spans1:
        chunk = by_chunk[span.chunk_id]
        assert chunk.text[span.char_start:span.char_end] == span.text
