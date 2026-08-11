from a3.domain.models import Evidence
from a3.indexing.chunking import ChunkPolicy, chunk_evidence


def test_chunks_and_spans_are_deterministic_exact_and_retain_locator():
    evidence = Evidence(id="MOCK-E1", source_type="trial", title="Mock",
        abstract_or_chunk="First synthetic sentence. 第二个合成句子。 Third synthetic sentence.",
        page="S12", section="mock methods", mock=True)
    policy = ChunkPolicy(version="test-policy", max_chars=40, overlap_chars=5, natural_boundary_ratio=.5)
    chunks1, spans1 = chunk_evidence(evidence, policy)
    chunks2, spans2 = chunk_evidence(evidence, policy)
    assert [c.chunk_id for c in chunks1] == [c.chunk_id for c in chunks2]
    assert len(chunks1) > 1
    assert chunks1[0].page is None and chunks1[0].raw_page == "S12"
    assert [s.span_id for s in spans1] == [s.span_id for s in spans2]
    by_chunk = {c.chunk_id: c for c in chunks1}
    for span in spans1:
        chunk = by_chunk[span.chunk_id]
        assert chunk.text[span.char_start:span.char_end] == span.text
        assert evidence.abstract_or_chunk[span.document_char_start:span.document_char_end] == span.text
        assert span.chunk_content_hash == chunk.content_hash
        assert span.evidence_content_hash == evidence.content_hash


def test_chinese_sentence_boundaries_do_not_require_spaces():
    evidence = Evidence(id="MOCK-ZH", source_type="review", title="Mock Chinese",
        abstract_or_chunk="第一句。第二句！第三句？第四句；", mock=True)
    policy = ChunkPolicy(version="zh", max_chars=1200, overlap_chars=0,
                         natural_boundary_ratio=.6)
    chunks, spans = chunk_evidence(evidence, policy)
    assert [span.text for span in spans] == ["第一句。", "第二句！", "第三句？", "第四句；"]
    assert all(chunks[0].text[span.char_start:span.char_end] == span.text for span in spans)
    assert all(evidence.abstract_or_chunk[span.document_char_start:span.document_char_end] == span.text
               for span in spans)
