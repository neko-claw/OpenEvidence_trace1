from core.models import Evidence
from retrieval.chunking import (
    ChunkPolicy,
    chunk_evidence,
    split_text,
)


def test_short_text_stays_one_chunk():
    policy = ChunkPolicy(
        max_chars=100,
        overlap_chars=20,
    )

    chunks = split_text(
        "Short hypertension evidence.",
        policy,
    )

    assert len(chunks) == 1


def test_long_text_is_split():
    policy = ChunkPolicy(
        max_chars=80,
        overlap_chars=10,
    )

    text = (
        "Hypertension is important. "
        "Blood pressure should be studied. "
        "Cardiovascular outcomes matter. "
        "Different populations may respond "
        "differently to treatment."
    )

    chunks = split_text(
        text,
        policy,
    )

    assert len(chunks) >= 2


def test_chunk_ids_are_deterministic():
    evidence = Evidence(
        id="E001",
        source_type="pubmed",
        title="Hypertension study",
        abstract_or_chunk=(
            "Hypertension evidence. "
            "Blood pressure evidence."
        ),
        pmid="12345678",
    )

    policy = ChunkPolicy(
        max_chars=30,
        overlap_chars=5,
    )

    first = chunk_evidence(
        evidence,
        policy,
    )

    second = chunk_evidence(
        evidence,
        policy,
    )

    assert [
        chunk.chunk_id
        for chunk in first
    ] == [
        chunk.chunk_id
        for chunk in second
    ]

    assert all(
        chunk.evidence_id == "E001"
        for chunk in first
    )

    assert all(
        chunk.content_hash
        for chunk in first
    )
