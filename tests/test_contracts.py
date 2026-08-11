import pytest

from a5.domain.enums import ClaimCriticality, MatchStatus, UncertaintyLevel
from a5.domain.models import Claim, EvidenceLike, EvidenceRecord
from a5.ports.evidence_retriever import EvidenceRetriever


class StructuralEvidence:
    id = "E-X"
    content = "Adapter-provided content"


class StructuralRetriever:
    def retrieve(self, question, plan, request):  # pragma: no cover
        raise NotImplementedError


def test_evidence_compatibility_model_keeps_unknown_fields_unknown() -> None:
    evidence = EvidenceRecord(
        id="E1", content="Mock evidence.", source_type="mock", title="Mock E1", mock=True
    )
    assert evidence.retrieval_score is None
    assert evidence.evidence_level is None
    assert evidence.published_at is None
    assert evidence.spans == []
    assert isinstance(StructuralEvidence(), EvidenceLike)


def test_claim_contract_defaults_do_not_fake_verification() -> None:
    claim = Claim(
        claim_id="C1", text="Atomic claim", criticality=ClaimCriticality.CRITICAL
    )
    assert claim.uncertainty is UncertaintyLevel.UNKNOWN
    assert claim.entailment_score is None
    assert claim.population_match is MatchStatus.UNKNOWN
    assert claim.time_match is MatchStatus.UNKNOWN
    assert claim.decision is None


def test_claim_rejects_duplicate_binding_ids() -> None:
    with pytest.raises(ValueError, match="identifier lists must contain unique values"):
        Claim(
            claim_id="C1",
            text="Atomic claim",
            criticality=ClaimCriticality.CRITICAL,
            evidence_ids=["E1", "E1"],
        )


def test_protocol_accepts_non_mock_structural_adapter() -> None:
    assert isinstance(StructuralRetriever(), EvidenceRetriever)
