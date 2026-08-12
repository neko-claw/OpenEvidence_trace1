from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from a1.adapters import A1SafetyPolicyAdapter
from a2.mcp.client import A2MCPClient
from a2.mcp.server import build_mcp_server
from a2.mcp.tools import A2ToolService
from a2.models.evidence import A2Evidence, SourceType
from a2.storage.dedup import compute_content_hash
from a2.storage.sqlite_store import SQLiteStore
from a3.indexing.embeddings import EmbeddingProvider
from a5.adapters.openai_compatible_claim_generator import OpenAICompatibleClaimGenerator
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.agent.workflow import A5Workflow
from a5.domain.models import AgentRun, Question
from a5.gates.evidence_integrity import EvidenceIntegrityGate
from a5.runtime_config import load_runtime_config
from backend.retriever import CoordinatedEvidenceRetriever
from backend.source import A2EvidenceSource
from retrieval.config import RetrievalConfig


ROOT = Path(__file__).resolve().parents[1]


class FixtureConnector:
    """Offline connector used only to exercise the real A2 MCP boundary."""

    def __init__(self, records: list[A2Evidence]) -> None:
        self.records = records
        self.calls = 0

    def search(self, _query: str, limit: int = 10) -> list[A2Evidence]:
        self.calls += 1
        return self.records[:limit]


class FixtureEmbeddingProvider:
    """Deterministic fixture vectorizer; never advertised as a medical model."""

    model_id = "MOCK-EMBEDDING-NOT-FOR-MEDICAL-USE"
    revision = "fixture-v1"
    source_kind = "offline_fixture"

    @staticmethod
    def _encode(text: str) -> list[float]:
        folded = text.casefold()
        return [
            float("synthetic" in folded),
            float("intervention" in folded),
            float("outcome" in folded),
            1.0,
        ]

    def encode_documents(self, texts):
        return [self._encode(text) for text in texts]

    def encode_queries(self, texts):
        return [self._encode(text) for text in texts]


class FixtureCalibratedQualityScorer:
    """Explicit fixture-only calibrated-quality Port for Gate2 control tests."""

    def score(self, _query, chunks):
        return {chunk.chunk_id: 0.92 for chunk in chunks}


class FixtureClaimTransport:
    """Select one exact retrieved Span through the production whitelist adapter."""

    def complete(self, *, model, messages, response_schema):
        del model, response_schema
        payload = json.loads(messages[-1]["content"])
        record = next(item for item in payload["evidence"] if item["spans"])
        span = record["spans"][0]
        return {
            "claims": [
                {
                    "claim_id": "MOCK-CLAIM-1",
                    "text": span["text"],
                    "criticality": "critical",
                    "evidence_ids": [record["id"]],
                    "evidence_span_ids": [span["span_id"]],
                    "uncertainty": "LOW",
                }
            ]
        }


def build_fixture_workflow(work_root: str | Path) -> A5Workflow:
    """Build the full offline A1->A2->A3->A4->A5 acceptance workflow."""

    root = Path(work_root)
    records = _fixture_records()
    empty = FixtureConnector([])
    service = A2ToolService(
        store=SQLiteStore(root / "a2.sqlite3"),
        pubmed=FixtureConnector([records[1]]),
        europe_pmc=empty,
        clinical_trials=empty,
        guidelines=FixtureConnector([records[0]]),
    )
    client = A2MCPClient(build_mcp_server(service))
    retriever = CoordinatedEvidenceRetriever(
        A2EvidenceSource(client),
        FixtureEmbeddingProvider(),
        index_root=root / "a3-vector",
        retrieval_config=RetrievalConfig(
            bm25_top_k=50,
            vector_top_k=50,
            fusion_top_k=80,
            rerank_top_k=25,
            selection_top_k=6,
        ),
        quality_scorer=FixtureCalibratedQualityScorer(),
    )
    config = load_runtime_config()
    generator = OpenAICompatibleClaimGenerator(
        transport=FixtureClaimTransport(),
        model="MOCK-STRUCTURED-GENERATOR",
        prompt_path=ROOT / "prompts" / "claim_generation_v0.4.0.md",
    )
    return A5Workflow(
        retriever=retriever,
        claim_generator=generator,
        claim_verifier=RuleBasedClaimVerifier(config.gates.gate5),
        safety_policy=A1SafetyPolicyAdapter(),
        evidence_integrity=EvidenceIntegrityGate(config.gates.gate1, allow_mock=True),
        runtime_config=config,
    )


def fixture_question() -> Question:
    return Question(
        question_id="MOCK-BACKEND-QUESTION",
        text="请检索治疗证据；这是合成协同测试，不是医学问题回答。",
        metadata={
            "as_of_date": "2026-08-11",
            "a1_safety_signals": {
                "topic": "hypertension",
                "acute_emergency": False,
                "personal_diagnosis": False,
                "personalized_prescribing_or_dose_change": False,
                "prompt_injection_or_fabricated_reference": False,
                "identifiable_personal_data": False,
                "special_population": "none",
            },
        },
    )


def run_fixture_demo(work_root: str | Path) -> AgentRun:
    return build_fixture_workflow(work_root).answer(fixture_question())


def main() -> None:
    work_root = ROOT / ".tmp" / "backend-demo"
    run = run_fixture_demo(work_root)
    artifact_root = ROOT / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    json_path = artifact_root / "backend_demo_trace.json"
    text_path = artifact_root / "backend_demo_trace.txt"
    json_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    text_path.write_text(_readable_trace(run), encoding="utf-8")
    print(f"decision={run.decision.value if run.decision else 'REFUSE'}")
    print(f"evidence={len(run.retrieved_evidence)} claims={len(run.claims)}")
    print(f"trace_json={json_path}")
    print(f"trace_text={text_path}")


def _fixture_records() -> list[A2Evidence]:
    now = datetime(2026, 8, 11, tzinfo=timezone.utc)
    raw: list[dict[str, Any]] = [
        {
            "id": "MOCK-BACKEND-GUIDELINE",
            "source_type": SourceType.GUIDELINE,
            "title": "[MOCK] Synthetic guideline source",
            "abstract_or_chunk": "Synthetic fixture: intervention A improved mock outcome B in mock adults.",
            "published_at": datetime(2025, 8, 1, tzinfo=timezone.utc),
            "evidence_level": "guideline",
            "fetched_at": now,
            "source_metadata": {"fixture_purpose": "backend_coordination"},
            "mock": True,
        },
        {
            "id": "MOCK-BACKEND-REVIEW",
            "source_type": SourceType.PUBMED,
            "title": "[MOCK] Synthetic review source",
            "abstract_or_chunk": "Synthetic fixture: an independent mock review discusses intervention A and mock outcome B.",
            "published_at": datetime(2025, 7, 1, tzinfo=timezone.utc),
            "evidence_level": "systematic_review",
            "fetched_at": now,
            "source_metadata": {"fixture_purpose": "backend_coordination"},
            "mock": True,
        },
    ]
    records: list[A2Evidence] = []
    for item in raw:
        records.append(A2Evidence.model_validate({**item, "content_hash": compute_content_hash(item)}))
    return records


def _readable_trace(run: AgentRun) -> str:
    lines = [
        "MOCK OFFLINE BACKEND COORDINATION TRACE — NOT MEDICAL EVIDENCE",
        f"run_id={run.run_id}",
        f"decision={run.decision.value if run.decision else 'REFUSE'}",
    ]
    for event in run.trace:
        parts = [event.timestamp.isoformat(), event.state.value, event.event_type.value]
        for name in ("gate", "skill", "tool", "decision"):
            value = getattr(event, name)
            if value is not None:
                parts.append(f"{name}={value}")
        if event.tool_call_index is not None:
            parts.append(f"tool_call_index={event.tool_call_index}")
        if event.tool_budget_remaining is not None:
            parts.append(f"budget_remaining={event.tool_budget_remaining}")
        lines.append(" | ".join(parts))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
