from __future__ import annotations

import json
from pathlib import Path

from a5.domain.models import Question, RetrievalRequest, SearchPlan
from backend.retriever import CoordinatedEvidenceRetriever
from backend.source import A2EvidenceSource
from retrieval.config import RetrievalConfig


ROOT = Path(__file__).resolve().parents[1]


class FixtureEmbeddingProvider:
    model_id = "MOCK-EMBEDDING-NOT-FOR-MEDICAL-USE"
    revision = "fixture-v1"
    source_kind = "offline_fixture"

    @staticmethod
    def _encode(text: str) -> list[float]:
        folded = text.casefold()
        return [
            float("synthetic" in folded),
            float("contract" in folded),
            1.0,
        ]

    def encode_documents(self, texts):
        return [self._encode(text) for text in texts]

    def encode_queries(self, texts):
        return [self._encode(text) for text in texts]


class FixtureQualityScorer:
    def score(self, _query, chunks):
        return {chunk.chunk_id: 0.91 for chunk in chunks}


class FixtureClient:
    def __init__(self) -> None:
        self.calls = 0
        self.response = json.loads(
            (ROOT / "contracts" / "a2" / "v1" / "fixtures" / "mock_tool_response.json")
            .read_text(encoding="utf-8")
        )

    def call_tool(self, _name, _arguments):
        self.calls += 1
        return self.response


def test_coordinated_retriever_runs_a2_a3_a4_without_score_relabeling(tmp_path) -> None:
    client = FixtureClient()
    retriever = CoordinatedEvidenceRetriever(
        A2EvidenceSource(client),
        FixtureEmbeddingProvider(),
        index_root=tmp_path / "vector",
        retrieval_config=RetrievalConfig(
            bm25_top_k=5,
            vector_top_k=5,
            fusion_top_k=5,
            rerank_top_k=5,
            selection_top_k=2,
        ),
        quality_scorer=FixtureQualityScorer(),
    )
    question = Question(
        question_id="MOCK-BACKEND-Q1",
        text="Synthetic content used to exercise the A2 to A3 contract.",
        metadata={"as_of_date": "2026-08-11"},
    )
    plan = SearchPlan(
        queries=["synthetic contract"],
        preferred_sources=["guideline"],
        freshness_required=False,
        expected_evidence_types=["guideline"],
        max_tool_calls=1,
    )

    result = retriever.retrieve(
        question, plan, RetrievalRequest(source_type="guideline", tool_call_index=1)
    )

    assert client.calls == 1
    assert retriever.call_count == 1
    assert result.evidence
    record = result.evidence[0]
    assert record.mock is True
    assert record.spans
    assert record.retrieval_score == 0.91
    assert record.retrieval_score_kind.value == "QUALITY"
    assert record.retrieval_score_scope.value == "CROSS_QUERY"
    assert record.source_metadata["ranking_score"] is not None
    assert result.diagnostics["pipeline"] == [
        "A2_MCP",
        "A2_TO_A3",
        "A3_INDEX",
        "A4_RETRIEVAL",
    ]
    assert result.diagnostics["a3"]["span_count"] >= 1
