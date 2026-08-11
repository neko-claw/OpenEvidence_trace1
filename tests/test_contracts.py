from a5.domain.enums import ClaimCriticality
from a5.domain.models import Claim, EvidenceLike, EvidenceRecord
from a5.ports.evidence_retriever import EvidenceRetriever


class StructuralEvidence:
    id = "E-X"
    content = "Adapter-provided content"


class StructuralRetriever:
    def retrieve(self, question, plan):  # pragma: no cover - contract check only
        raise NotImplementedError


def test_evidence_compatibility_model_is_explicitly_mockable() -> None:
    evidence = EvidenceRecord(
        id="E1",
        content="Mock evidence content.",
        source_type="mock",
        title="Mock evidence E1",
        mock=True,
    )
    assert evidence.mock is True
    assert isinstance(StructuralEvidence(), EvidenceLike)


def test_claim_rejects_duplicate_evidence_ids() -> None:
    try:
        Claim(
            claim_id="C1",
            text="Atomic claim.",
            criticality=ClaimCriticality.CRITICAL,
            evidence_ids=["E1", "E1"],
        )
    except ValueError as exc:
        assert "evidence_ids must be unique" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("duplicate IDs must fail validation")


def test_protocol_accepts_non_mock_structural_adapter() -> None:
    assert isinstance(StructuralRetriever(), EvidenceRetriever)
