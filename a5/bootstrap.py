from __future__ import annotations

from a5.adapters.default_safety_policy import DefaultSafetyPolicy
from a5.adapters.mock_claim_generator import MockClaimGenerator
from a5.adapters.mock_evidence_retriever import MockEvidenceRetriever
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.agent.workflow import A5Workflow


def build_demo_workflow() -> A5Workflow:
    """Composition root for the offline demo only; never use as production wiring."""

    return A5Workflow(
        retriever=MockEvidenceRetriever(),
        claim_generator=MockClaimGenerator(),
        claim_verifier=RuleBasedClaimVerifier(),
        safety_policy=DefaultSafetyPolicy(),
    )
