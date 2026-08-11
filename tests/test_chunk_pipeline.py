from core.models import Evidence
from retrieval.chunking import ChunkPolicy
from scripts.build_chunks import build_chunks
from storage.database import EvidenceDatabase


def test_evidence_to_current_chunks_pipeline(
    tmp_path,
):
    db_path = tmp_path / "pipeline.db"

    evidence = Evidence(
        id="E001",
        source_type="pubmed",
        title="Hypertension evidence",
        abstract_or_chunk=(
            "Hypertension is a cardiovascular "
            "risk factor. Blood pressure control "
            "may reduce cardiovascular risk."
        ),
        pmid="12345678",
    )

    with EvidenceDatabase(db_path) as db:
        db.init_schema()

        inserted = db.insert_evidence(
            evidence
        )

        assert inserted is True

    report = build_chunks(
        db_path=str(db_path),
        policy=ChunkPolicy(
            max_chars=80,
            overlap_chars=10,
        ),
    )

    assert report["evidence_processed"] == 1
    assert report["chunks_inserted"] >= 1

    with EvidenceDatabase(db_path) as db:
        db.init_schema()

        chunks = db.list_current_chunks()

        assert len(chunks) >= 1

        assert all(
            chunk["evidence_id"] == "E001"
            for chunk in chunks
        )

        assert all(
            chunk["title"]
            == "Hypertension evidence"
            for chunk in chunks
        )
