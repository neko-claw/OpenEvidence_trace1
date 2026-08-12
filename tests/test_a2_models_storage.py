from __future__ import annotations

from datetime import datetime, timezone

from a2.models.evidence import A2Evidence, SourceType
from a2.storage.cache import make_cache_key
from a2.storage.dedup import canonical_key, compute_content_hash, normalize_doi
from a2.storage.jsonl_export import export_jsonl
from a2.storage.sqlite_store import SQLiteStore


def evidence(**updates) -> A2Evidence:
    data = {
        "id": "PMID:31452104",
        "source_type": SourceType.PUBMED,
        "title": "Molegro Virtual Docker for Docking.",
        "abstract_or_chunk": "Molegro Virtual Docker is a protein-ligand docking simulation program.",
        "pmid": "31452104",
        "doi": "10.1007/978-1-4939-9752-7_10",
        "published_at": datetime(2019, 1, 1, tzinfo=timezone.utc),
    }
    data.update(updates)
    data["content_hash"] = compute_content_hash(data)
    return A2Evidence.model_validate(data)


def test_doi_normalization_and_canonical_priority() -> None:
    assert normalize_doi(" HTTPS://DOI.ORG/10.1007/ABC ") == "10.1007/abc"
    assert normalize_doi("doi: 10.1007/ABC") == "10.1007/abc"
    assert canonical_key(evidence(doi="https://doi.org/10.1007/978-1-4939-9752-7_10")) == "DOI:10.1007/978-1-4939-9752-7_10"


def test_content_hash_stable_across_fetch_times_and_changes_with_content() -> None:
    first = evidence(fetched_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    second = evidence(fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    changed = evidence(abstract_or_chunk="Changed public-record content.")
    assert first.content_hash == second.content_hash
    assert changed.content_hash != first.content_hash


def test_sqlite_dedup_merges_same_doi_and_preserves_alias_conflict(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "a2.sqlite3")
    first = store.put(evidence())
    incoming = evidence(
        id="EPMC:MED:31452104", source_type=SourceType.EUROPE_PMC,
        title="Conflicting title retained as diagnostic", pmid="31452104",
    )
    merged = store.put(incoming)
    assert len(store.list_evidence()) == 1
    assert store.get("EPMC:MED:31452104").id == first.id
    assert "EPMC:MED:31452104" in merged.source_metadata["aliases"]
    assert any(item["field"] == "title" for item in merged.source_metadata["dedup_conflicts"])


def test_distinct_records_remain_distinct(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "a2.sqlite3")
    store.put(evidence())
    trial = evidence(
        id="NCT:NCT03036124", source_type=SourceType.CLINICAL_TRIALS,
        title="Study to Evaluate the Effect of Dapagliflozin on Chronic Heart Failure",
        abstract_or_chunk="The purpose is to evaluate dapagliflozin.",
        pmid=None, doi=None, nct_id="NCT03036124",
    )
    store.put(trial)
    assert len(store.list_evidence()) == 2


def test_http_cache_key_is_deterministic_and_excludes_secret_values() -> None:
    first = make_cache_key("GET", "HTTPS://EXAMPLE.ORG/path", {"b": 2, "api_key": "secret-one", "a": 1})
    second = make_cache_key("get", "https://example.org/path", {"a": 1, "api_key": "secret-two", "b": 2})
    assert first == second


def test_jsonl_export_round_trips_deterministically(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "a2.sqlite3")
    expected = store.put(evidence())
    target = tmp_path / "evidence.jsonl"
    assert export_jsonl(store, target) == 1
    parsed = A2Evidence.model_validate_json(target.read_text(encoding="utf-8").strip())
    assert parsed == expected
