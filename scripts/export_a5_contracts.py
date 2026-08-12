from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from a5.adapters.default_safety_policy import FixtureSafetyPolicy
from a5.adapters.mock_claim_generator import MockClaimGenerator
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.agent.workflow import A5Workflow
from a5.bootstrap import build_demo_workflow
from a5.domain.models import AgentRun, AgentRunView, Question
from a5.gates.evidence_integrity import EvidenceIntegrityGate
from a5.runtime_config import load_runtime_config

OUTPUT = ROOT / "contracts" / "a5" / "v0.4.0"


class ExplodingRetriever:
    def retrieve(self, question, plan, request):
        del question, plan, request
        raise RuntimeError("fixture upstream unavailable")


def _question(case: str) -> Question:
    batches = {
        "pass": [["E1"], ["E2"]],
        "warn": [["E1"], ["E3"]],
        "refuse": [[], [], []],
    }[case]
    return Question(
        question_id=f"Q-REPLAY-{case.upper()}",
        text=f"Artificial offline {case} replay question.",
        metadata={
            "fixture_batches": batches,
            "mock_safety_decision": "ALLOW",
            "as_of_date": "2026-08-12",
            "demo_mode": True,
        },
    )


def _error_run() -> AgentRun:
    config = load_runtime_config()
    workflow = A5Workflow(
        retriever=ExplodingRetriever(),
        claim_generator=MockClaimGenerator(),
        claim_verifier=RuleBasedClaimVerifier(config.gates.gate5),
        safety_policy=FixtureSafetyPolicy(config.gates.gate0_version),
        evidence_integrity=EvidenceIntegrityGate(config.gates.gate1, allow_mock=True),
        runtime_config=config,
    )
    return workflow.answer(
        Question(
            question_id="Q-REPLAY-ERROR",
            text="Artificial offline error replay question.",
            metadata={"mock_safety_decision": "ALLOW", "as_of_date": "2026-08-12"},
        )
    )


def main() -> None:
    schema_dir = OUTPUT / "schemas"
    fixture_dir = OUTPUT / "fixtures"
    schema_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir.mkdir(parents=True, exist_ok=True)
    for name, model in {"AgentRun": AgentRun, "AgentRunView": AgentRunView}.items():
        (schema_dir / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    workflow = build_demo_workflow()
    runs = {case: workflow.answer(_question(case)) for case in ("pass", "warn", "refuse")}
    runs["error"] = _error_run()
    for case, run in runs.items():
        (fixture_dir / f"{case}.json").write_text(
            run.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
