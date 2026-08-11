from datetime import datetime, timezone

from a3.domain.models import Evidence
from a3.indexing.bm25 import BM25Index, tokenize
from a3.indexing.chunking import chunk_evidence


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
    evidence = records(); chunks = sum((chunk_evidence(e)[0] for e in evidence), [])
    index = BM25Index.build(evidence, chunks, "idx")
    assert index.search("blood-pressure", 3)[0].evidence_id == "M1"
    assert index.search("unfindable", 3) == []
    loaded = BM25Index.load(index.save(tmp_path))
    assert loaded.search("胆固醇 cholesterol", 1)[0].evidence_id == "M2"
    assert loaded.search("synthetic", 5, {"source_type":"review","date_to":"2024-12-31"})[0].evidence_id == "M1"
    assert loaded.search("synthetic", 5, {"date_from":"2027-01-01"}) == []
