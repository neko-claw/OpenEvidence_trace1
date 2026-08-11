from a3.domain.models import Evidence
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from a3.indexing.bm25 import BM25Index
from a3.storage.sqlite_store import SQLiteEvidenceStore
from tests.a3_support import make_manifest


def item(text="Synthetic pipeline text.", tombstone=False):
    return Evidence(id="MOCK-E001", source_type="review", title="Mock", abstract_or_chunk=text,
                    upstream_id="MOCK-E001", mock=True, tombstone=tombstone)


POLICY = ChunkPolicy(version="test", max_chars=1200, overlap_chars=150, natural_boundary_ratio=.6)


def test_immutable_versions_dedup_current_and_tombstone(tmp_path):
    with SQLiteEvidenceStore(tmp_path / "a3.db") as store:
        first = item()
        assert store.insert_evidence(first)
        assert not store.insert_evidence(first)
        changed = item("Changed synthetic pipeline text.")
        assert store.insert_evidence(changed)
        assert store.list_current_evidence()[0].content_hash == changed.content_hash
        chunks, spans = chunk_evidence(changed, POLICY)
        store.replace_chunks(changed, chunks, spans)
        store.replace_chunks(changed, chunks, spans)
        assert len(store.list_current_chunks()) == 1
        assert store.list_spans_for_evidence(changed.id)[0].text in changed.abstract_or_chunk
        assert store.insert_evidence(item("Removed.", tombstone=True))
        assert store.list_current_evidence() == []
        assert store.list_current_chunks() == [] and store.list_current_spans() == []
        current_evidence = store.list_current_evidence()
        rebuilt = BM25Index.build(current_evidence, store.list_current_chunks(),
            store.list_current_spans(), make_manifest(current_evidence))
        assert rebuilt.search("Changed", 5) == []
