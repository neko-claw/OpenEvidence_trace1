from __future__ import annotations

import pytest

from retrieval.models import EvidenceChunk


@pytest.fixture
def evidence_chunks() -> tuple[EvidenceChunk, ...]:
    """Small clinical corpus shared by retrieval primitive tests."""
    return (
        EvidenceChunk(
            chunk_id="chunk-amlodipine",
            evidence_id="evidence-amlodipine",
            stable_id="upstream:MOCK-A4-AMLODIPINE",
            title="Amlodipine for hypertension in older adults",
            text="A randomized trial found amlodipine reduced systolic blood pressure in older adults.",
            source_type="pubmed",
            evidence_level="rct",
            mock=True,
        ),
        EvidenceChunk(
            chunk_id="chunk-losartan",
            evidence_id="evidence-losartan",
            stable_id="upstream:MOCK-A4-LOSARTAN",
            title="Losartan treatment for hypertension",
            text="Losartan improved blood pressure control in adults with hypertension.",
            source_type="pubmed",
            evidence_level="rct",
            mock=True,
        ),
        EvidenceChunk(
            chunk_id="chunk-chinese",
            evidence_id="evidence-chinese",
            stable_id="upstream:MOCK-A4-GUIDELINE",
            title="老年高血压患者的药物治疗建议",
            text="该指南讨论老年高血压患者的降压治疗与随访。",
            source_type="guideline",
            evidence_level="guideline",
            mock=True,
        ),
    )
