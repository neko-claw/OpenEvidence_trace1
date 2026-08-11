"""Behavioral tests for the SQLite evidence store (4.1 storage/version/tombstone)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from retrieval.models import EvidenceChunk
from retrieval.store import EvidenceStore


def _chunk(chunk_id: str, **changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": f"evidence-{chunk_id}",
        "stable_id": f"PMID:{chunk_id}",
        "text": f"Clinical evidence snippet {chunk_id}.",
        "source_type": "pubmed",
        "evidence_level": "rct",
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


def test_store_upserts_new_chunks_and_dedupes_by_content_hash(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    stats = store.upsert_chunks((_chunk("c1"), _chunk("c2"), _chunk("c1")))

    assert stats.inserted == 2
    assert stats.unchanged == 1
    assert stats.duplicates_skipped == 0
    assert len(store.load_chunks()) == 2

    # identical content under a different chunk id is skipped by content hash
    copy = replace(_chunk("c1"), chunk_id="c1-copy")
    stats = store.upsert_chunks((copy,))

    assert stats.duplicates_skipped == 1
    assert len(store.load_chunks()) == 2


def test_store_unchanged_hash_is_counted_and_not_rewritten(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    store.upsert_chunks((_chunk("c1"),))
    stats = store.upsert_chunks((_chunk("c1"),))

    assert stats.inserted == 0
    assert stats.unchanged == 1


def test_store_updates_changed_content_and_reports_update(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    store.upsert_chunks((_chunk("c1"),))
    changed = replace(_chunk("c1"), text="Updated clinical evidence text.")
    stats = store.upsert_chunks((changed,))

    assert stats.updated == 1
    assert stats.inserted == 0
    chunks = store.load_chunks()
    assert len(chunks) == 1
    assert chunks[0].text == "Updated clinical evidence text."
    # A3 hash 保留调用方提供的值（不覆盖）；内容版本由派生 hash 检测。
    assert chunks[0].content_hash == _chunk("c1").content_hash
    assert chunks[0].content_hash_mismatch is True
    assert chunks[0].derived_content_hash != chunks[0].content_hash


def test_store_detects_content_change_via_derived_hash_not_stale_supplied_hash(tmp_path) -> None:
    """评审项 6：replace() 遗留的旧 content_hash 不得掩盖内容更新。"""
    store = EvidenceStore(tmp_path / "evidence.db")
    store.upsert_chunks((_chunk("c1"),))
    # 调用方显式传入一个陈旧 hash（与内容不一致）——store 仍必须检测内容变化。
    stale = EvidenceChunk(
        chunk_id="c1",
        evidence_id="evidence-c1",
        stable_id="PMID:c1",
        text="Completely different content now.",
        source_type="pubmed",
        evidence_level="rct",
        content_hash=_chunk("c1").content_hash,
    )
    stats = store.upsert_chunks((stale,))

    assert stats.updated == 1
    loaded = store.load_chunks()[0]
    assert loaded.text == "Completely different content now."
    # 上游提供的 hash 未被覆盖，且不一致被显式标记。
    assert loaded.content_hash == _chunk("c1").content_hash
    assert loaded.content_hash_mismatch is True


def test_store_skips_chunks_for_tombstoned_stable_ids(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    store.upsert_chunks((_chunk("c1"),))
    assert store.tombstone("PMID:c1") is True
    assert store.tombstone("PMID:c1") is False  # already tombstoned

    stats = store.upsert_chunks((_chunk("c1"),))

    assert stats.tombstoned_skipped == 1
    assert store.load_chunks() == ()


def test_store_load_chunks_applies_metadata_filters(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    store.upsert_chunks(
        (
            _chunk("pub-rct", source_type="pubmed", evidence_level="rct", topic="hypertension"),
            _chunk("guide", source_type="guideline", evidence_level="guideline", topic="hypertension"),
            _chunk("lipid", source_type="pubmed", evidence_level="rct", topic="lipid"),
        )
    )

    assert {c.chunk_id for c in store.load_chunks(source_types=("pubmed",))} == {"pub-rct", "lipid"}
    assert {c.chunk_id for c in store.load_chunks(evidence_levels=("guideline",))} == {"guide"}
    assert {c.chunk_id for c in store.load_chunks(topic="hypertension")} == {"pub-rct", "guide"}


def test_store_load_chunks_filters_by_published_after(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    store.upsert_chunks(
        (
            _chunk("old", published_at="2019-01-01"),
            _chunk("new", published_at="2024-01-01"),
            _chunk("nodate"),
        )
    )

    assert {c.chunk_id for c in store.load_chunks(published_after="2020-01-01")} == {"new"}


def test_store_round_trip_preserves_pico_and_versions(tmp_path) -> None:
    store = EvidenceStore(
        tmp_path / "evidence.db",
        index_version="idx-v2",
        corpus_version="corpus-v2",
        embedding_model="bge-m3",
        chunk_policy="p256-ov10",
    )
    chunk = _chunk("c1", pico_population=("older adults",), pico_intervention=("amlodipine",), topic="hypertension")
    store.upsert_chunks((chunk,))

    loaded = store.load_chunks()

    assert len(loaded) == 1
    assert loaded[0].pico_population == ("older adults",)
    assert loaded[0].pico_intervention == ("amlodipine",)
    assert loaded[0].index_version == "idx-v2"
    assert loaded[0].corpus_version == "corpus-v2"
    assert loaded[0].topic == "hypertension"


def test_store_records_and_reads_index_versions(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db")
    store.record_version("idx-20260811-v1", corpus_hash="abc123", embedding_model="bge-m3", chunk_policy="p256-ov10")

    version = store.get_version("idx-20260811-v1")

    assert version is not None
    assert version["corpus_hash"] == "abc123"
    assert version["embedding_model"] == "bge-m3"
    assert store.get_version("missing") is None


def test_store_rejects_mismatched_corpus_version_on_load(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "evidence.db", index_version="idx-v1", corpus_version="corpus-v1")
    store.upsert_chunks((_chunk("c1"),))

    with pytest.raises(ValueError, match="corpus"):
        store.load_chunks(require_versions=("idx-v1", "corpus-v2"))


def test_store_is_reopenable_and_persistent(tmp_path) -> None:
    path = tmp_path / "evidence.db"
    EvidenceStore(path).upsert_chunks((_chunk("c1"),))
    reopened = EvidenceStore(path, index_version="idx-v1", corpus_version="corpus-v1")

    assert len(reopened.load_chunks()) == 1


def test_store_round_trips_gate1_provenance_fields(tmp_path) -> None:
    chunk = _chunk(
        "c-gate",
        stable_id="PMID:33000020",
        title="Amlodipine in older adults",
        url="https://pubmed.ncbi.nlm.nih.gov/33000020/",
        published_at="2024-06-01",
        pmid="33000020",
        doi="10.1000/example.2024.06.001",
        nct_id="",
        authors=("Wang H", "Li Y", "Chen J"),
        guideline_name="",
        fetched_at="2026-08-10T09:00:00Z",
    )
    store = EvidenceStore(tmp_path / "gate.db")

    store.upsert_chunks((chunk,))
    loaded = store.load_chunks()[0]

    assert loaded.pmid == "33000020"
    assert loaded.doi == "10.1000/example.2024.06.001"
    assert loaded.authors == ("Wang H", "Li Y", "Chen J")
    assert loaded.guideline_name == ""
    assert loaded.fetched_at == "2026-08-10T09:00:00Z"


def test_store_enforces_source_gate_and_counts_skipped(tmp_path) -> None:
    complete = _chunk(
        "c-ok",
        url="https://pubmed.ncbi.nlm.nih.gov/1/",
        published_at="2024-01-01",
        fetched_at="2026-08-10T09:00:00Z",
    )
    missing_fetched = replace(complete, chunk_id="c-no-fetch", fetched_at=None)
    missing_url = replace(complete, chunk_id="c-no-url", url="")
    store = EvidenceStore(tmp_path / "gated.db", enforce_source_gate=True)

    stats = store.upsert_chunks((complete, missing_fetched, missing_url))
    loaded = store.load_chunks()

    assert stats.gate_skipped == 2
    assert stats.inserted == 1
    assert [chunk.chunk_id for chunk in loaded] == ["c-ok"]


def test_store_without_gate_enforcement_accepts_partial_provenance(tmp_path) -> None:
    partial = _chunk("c-partial", fetched_at=None, url="")
    store = EvidenceStore(tmp_path / "loose.db")

    stats = store.upsert_chunks((partial,))

    assert stats.inserted == 1
    assert len(store.load_chunks()) == 1
