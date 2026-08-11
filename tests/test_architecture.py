from pathlib import Path

from a5.adapters.default_safety_policy import DefaultFailClosedSafetyPolicy
from a5.adapters.mock_claim_generator import MockClaimGenerator
from a5.adapters.mock_evidence_retriever import MockEvidenceRetriever
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.ports.claim_generator import ClaimGenerator
from a5.ports.claim_verifier import ClaimVerifier
from a5.ports.evidence_retriever import EvidenceRetriever
from a5.ports.safety_policy import SafetyPolicy


def test_adapters_satisfy_structural_ports() -> None:
    assert isinstance(MockEvidenceRetriever(), EvidenceRetriever)
    assert isinstance(MockClaimGenerator(), ClaimGenerator)
    assert isinstance(RuleBasedClaimVerifier(), ClaimVerifier)
    assert isinstance(DefaultFailClosedSafetyPolicy(), SafetyPolicy)


def test_workflow_depends_on_ports_not_mock_or_upstream_concretes() -> None:
    source = (Path(__file__).parents[1] / "a5/agent/workflow.py").read_text(encoding="utf-8")
    assert "MockEvidenceRetriever" not in source
    assert "MockClaimGenerator" not in source
    assert "a5.adapters" not in source
    assert "A2MCP" not in source
    assert "A4RAG" not in source


def test_workflow_dependencies_are_typed_as_ports() -> None:
    source = (Path(__file__).parents[1] / "a5/agent/workflow.py").read_text(encoding="utf-8")
    assert "self._retriever: EvidenceRetriever" in source
    assert "self._claim_generator: ClaimGenerator" in source
    assert "self._safety_policy: SafetyPolicy" in source
