from __future__ import annotations

from a5.adapters.default_safety_policy import (
    DefaultFailClosedSafetyPolicy,
    FixtureSafetyPolicy,
)
from a5.adapters.mock_claim_generator import MockClaimGenerator
from a5.adapters.mock_evidence_retriever import MockEvidenceRetriever
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.agent.workflow import A5Workflow
from a5.gates.evidence_integrity import EvidenceIntegrityGate
from a5.runtime_config import RuntimeConfig, load_runtime_config


def _build(config: RuntimeConfig, *, demo: bool) -> A5Workflow:
    return A5Workflow(
        retriever=MockEvidenceRetriever(),
        claim_generator=MockClaimGenerator(),
        claim_verifier=RuleBasedClaimVerifier(
            config.gates.gate5,
            name=config.models.claim_verifier,
            textual_support_name=config.models.textual_support_evaluator,
        ),
        safety_policy=(
            FixtureSafetyPolicy(config.gates.gate0_version)
            if demo
            else DefaultFailClosedSafetyPolicy(config.gates.gate0_version)
        ),
        evidence_integrity=EvidenceIntegrityGate(config.gates.gate1, allow_mock=demo),
        runtime_config=config,
    )


def build_demo_workflow() -> A5Workflow:
    """Offline fixture wiring with explicit mock Gate0 decisions."""
    return _build(load_runtime_config(), demo=True)


def build_default_workflow() -> A5Workflow:
    """Fail-closed wiring until an A1 SafetyPolicy adapter is provided."""
    return _build(load_runtime_config(), demo=False)
