from core.models import Evidence
from storage.database import EvidenceDatabase


def make_evidence(
    text: str = "Original abstract",
) -> Evidence:
    return Evidence(
        id="E001",
        source_type="pubmed",
        title="Hypertension study",
        abstract_or_chunk=text,
        authors=["Alice", "Bob"],
        pmid="12345678",
        population="Adults with hypertension",
    )


def test_insert_and_get_evidence(tmp_path):
    db_path = tmp_path / "test.db"

    evidence = make_evidence()

    with EvidenceDatabase(db_path) as db:
        db.init_schema()

        inserted = db.insert_evidence(evidence)

        assert inserted is True
        assert db.count_evidence() == 1

        result = db.get_latest_evidence("E001")

        assert result is not None
        assert result["pmid"] == "12345678"
        assert result["title"] == "Hypertension study"


def test_duplicate_evidence_is_ignored(tmp_path):
    db_path = tmp_path / "test.db"

    evidence = make_evidence()

    with EvidenceDatabase(db_path) as db:
        db.init_schema()

        first = db.insert_evidence(evidence)
        second = db.insert_evidence(evidence)

        assert first is True
        assert second is False
        assert db.count_evidence() == 1


def test_changed_content_creates_new_version(tmp_path):
    db_path = tmp_path / "test.db"

    old = make_evidence(
        "Original abstract"
    )

    new = make_evidence(
        "Updated abstract"
    )

    with EvidenceDatabase(db_path) as db:
        db.init_schema()

        first = db.insert_evidence(old)
        second = db.insert_evidence(new)

        assert first is True
        assert second is True

        assert old.content_hash != new.content_hash

        assert db.count_evidence() == 2
