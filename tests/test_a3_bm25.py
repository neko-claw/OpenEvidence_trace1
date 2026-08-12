from datetime import datetime, timezone

from a3.domain.models import Evidence
from a3.indexing.bm25 import BM25Index, tokenize
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from tests.a3_support import make_manifest
from a3.wiki.generator import WikiLexicalDocument

POLICY = ChunkPolicy(version="test", max_chars=1200, overlap_chars=150, natural_boundary_ratio=.6)


def records():
    return [
        Evidence(id="M1", source_type="review", title="Hypertension mock", abstract_or_chunk="blood-pressure synthetic pipeline text 高血压合成文本。", published_at=datetime(2024,1,1,tzinfo=timezone.utc), mock=True),
        Evidence(id="M2", source_type="trial", title="Lipids mock", abstract_or_chunk="cholesterol synthetic pipeline text.", published_at=datetime(2026,1,1,tzinfo=timezone.utc), mock=True),
    ]


def test_bilingual_identifier_tokenizer():
    tokens = tokenize("nct:MOCK-ABC pmid:LOCAL 高血压")
    assert "nct:mock-abc" in tokens and "mock-abc" in tokens
    assert "高血" in tokens and "血压" in tokens


def test_bm25_search_save_load_and_no_match(tmp_path):
    evidence = records(); chunked = [chunk_evidence(item, POLICY) for item in evidence]
    chunks = sum((item[0] for item in chunked), []); spans = sum((item[1] for item in chunked), [])
    manifest = make_manifest(evidence)
    index = BM25Index.build(evidence, chunks, spans, manifest)
    hit = index.search("blood-pressure", 3)[0]
    assert hit.evidence_id == "M1" and hit.mock and hit.live_state == "live"
    assert hit.chunk_content_hash == chunks[0].content_hash
    assert hit.evidence_content_hash == evidence[0].content_hash
    assert hit.span_refs and hit.corpus_version == manifest.corpus_version
    assert index.search("unfindable", 3) == []
    loaded = BM25Index.load(index.save(tmp_path))
    assert loaded.search("胆固醇 cholesterol", 1)[0].evidence_id == "M2"
    assert loaded.search("synthetic", 5, {"source_type":"review","date_to":"2024-12-31"})[0].evidence_id == "M1"
    assert loaded.search("synthetic", 5, {"date_from":"2027-01-01"}) == []


def test_wiki_navigation_is_typed_and_never_evidence():
    evidence = records()[:1]; chunks, spans = chunk_evidence(evidence[0], POLICY)
    manifest = make_manifest(evidence)
    wiki = WikiLexicalDocument(slug="pressure", title="Pressure", text="pressure alias",
                               relative_path="pressure.md")
    hit = BM25Index.build(evidence, chunks, spans, manifest, [wiki]).search("alias", 1)[0]
    assert hit.document_kind == "wiki_navigation" and hit.evidence_id is None
    assert hit.mock and hit.tombstone is None and hit.live_state == "navigation_only"
    assert hit.span_refs == [] and hit.metadata["navigation_only"] is True
