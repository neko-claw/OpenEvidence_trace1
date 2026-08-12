from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from a3.domain.models import Evidence


def evidence(**updates):
    data = dict(id="E1", source_type="review", title="Synthetic title",
                abstract_or_chunk="Synthetic pipeline text.", mock=True)
    data.update(updates)
    return Evidence(**data)


def test_stable_id_and_content_hash_are_deterministic_and_ignore_fetch_time():
    a = evidence(fetched_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    b = evidence(fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert a.stable_id == "upstream:E1"
    assert a.content_hash == b.content_hash


def test_real_identifier_priority():
    item = Evidence(
        id="PMID:31452104",
        source_type="study",
        title="Molegro Virtual Docker for Docking.",
        abstract_or_chunk="Molegro Virtual Docker is a protein-ligand docking simulation program.",
        pmid="31452104",
    )
    assert item.stable_id == "pmid:31452104"


def test_mock_guard_rejects_identifiers():
    with pytest.raises(ValidationError):
        evidence(pmid="31452104")
