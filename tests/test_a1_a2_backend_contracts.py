from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from a1.adapters import A1SafetyPolicyAdapter, SafetyClassificationRequest
from a1.models import SafetyPolicyInput
from a2.adapters import A2ToA3NormalizationError, A2ToA3Normalizer
from a2.export_schemas import rendered_schemas
from a2.mcp.tools import A2ToolService
from a2.models import A2Error, A2ErrorCode, A2Evidence, ToolDiagnostics, ToolResponse
from a2.storage.sqlite_store import SQLiteStore
from a3.domain.models import Evidence as A3Evidence
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from a5.adapters.a3 import adapt_a3_selection
from a5.domain.enums import SafetyDecision
from a5.domain.models import Question
from tests.a3_support import make_manifest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "a2" / "v1"


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((CONTRACT / "fixtures" / name).read_text(encoding="utf-8"))


class CompleteSignalClassifier:
    def __init__(self) -> None:
        self.requests: list[SafetyClassificationRequest] = []

    def classify(self, request: SafetyClassificationRequest) -> SafetyPolicyInput:
        self.requests.append(request)
        return SafetyPolicyInput(
            question_id=request.question_id,
            topic="hypertension",
            acute_emergency=False,
            personal_diagnosis=False,
            personalized_prescribing_or_dose_change=False,
            prompt_injection_or_fabricated_reference=False,
            identifiable_personal_data=False,
            special_population="none",
        )


class BrokenSignalClassifier:
    def classify(self, request: SafetyClassificationRequest) -> object:
        del request
        raise RuntimeError("classifier unavailable")


def test_a1_plain_question_requires_injected_classifier_and_remains_fail_closed() -> None:
    question = Question(question_id="Q-PLAIN", text="高血压相关证据是什么？")
    missing = A1SafetyPolicyAdapter().assess(question)
    broken = A1SafetyPolicyAdapter(classifier=BrokenSignalClassifier()).assess(question)
    assert missing.decision is SafetyDecision.UNKNOWN
    assert broken.decision is SafetyDecision.UNKNOWN


def test_a1_injected_classifier_produces_only_normalized_gate0_signals() -> None:
    classifier = CompleteSignalClassifier()
    result = A1SafetyPolicyAdapter(classifier=classifier).assess(
        Question(question_id="Q-CLASSIFIED", text="高血压机制的公开研究证据是什么？")
    )
    assert result.decision is SafetyDecision.ALLOW
    assert classifier.requests == [
        SafetyClassificationRequest(
            question_id="Q-CLASSIFIED",
            text="高血压机制的公开研究证据是什么？",
        )
    ]


def test_a2_checked_in_schemas_match_pydantic_source_and_validate_fixtures() -> None:
    fixtures = {
        "Evidence.schema.json": load_fixture("mock_evidence.json"),
        "ToolResponse.schema.json": load_fixture("mock_tool_response.json"),
    }
    for filename, rendered in rendered_schemas().items():
        checked_in = (CONTRACT / "schemas" / filename).read_text(encoding="utf-8")
        assert checked_in == rendered
        schema = json.loads(checked_in)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(fixtures[filename])

    A2Evidence.model_validate(fixtures["Evidence.schema.json"])
    ToolResponse.model_validate(fixtures["ToolResponse.schema.json"])


def test_a2_mock_contract_is_explicit_and_forbids_external_identity() -> None:
    item = A2Evidence.model_validate(load_fixture("mock_evidence.json"))
    assert item.mock is True
    # Adversarial construction with a verified identifier must be rejected.
    with pytest.raises(ValidationError, match="mock evidence cannot carry"):
        A2Evidence.model_validate({**item.model_dump(), "pmid": "31452104"})


def test_a2_to_a3_normalizer_preserves_provenance_without_inventing_semantics() -> None:
    source = A2Evidence.model_validate(load_fixture("mock_evidence.json"))
    mapped = A2ToA3Normalizer().normalize(source)
    validated = A3Evidence.model_validate(mapped)

    assert validated.mock is True
    assert validated.population is None
    assert validated.intervention is None
    assert validated.comparator is None
    assert validated.outcome is None
    assert validated.evidence_level is None
    assert mapped["provenance"]["a2_content_hash"] == source.content_hash
    assert mapped["provenance"]["fixture"] is True
    assert "content_hash" not in mapped
    assert "spans" not in mapped and "chunk_id" not in mapped
    assert "verified" not in mapped and "trust" not in mapped
    assert "semantic_verified" not in mapped["provenance"]


def test_a2_mock_normalizer_reaches_a3_to_a5_without_synthetic_span_or_score() -> None:
    source = A2Evidence.model_validate(load_fixture("mock_evidence.json"))
    a3_evidence = A3Evidence.model_validate(A2ToA3Normalizer().normalize(source))
    chunks, _generated_spans = chunk_evidence(
        a3_evidence,
        ChunkPolicy(
            version="a2-a3-contract-test",
            max_chars=256,
            overlap_chars=0,
            natural_boundary_ratio=0.5,
        ),
    )
    manifest = make_manifest([a3_evidence])

    adapted = adapt_a3_selection(
        a3_evidence,
        chunks,
        [],
        manifest,
        index_version=manifest.index_version,
        corpus_version=manifest.corpus_version,
    )

    assert adapted.evidence.mock is True
    assert adapted.evidence.spans == []
    assert adapted.evidence.retrieval_score is None
    assert adapted.evidence.evidence_level is None
    assert adapted.evidence.source_metadata["provenance"]["fixture"] is True


def test_a2_tool_response_normalizer_distinguishes_empty_and_error() -> None:
    normalizer = A2ToA3Normalizer()
    empty = ToolResponse(
        ok=True,
        evidence=[],
        diagnostics=ToolDiagnostics(tool_name="search_pubmed", result_count=0),
    )
    assert normalizer.normalize_tool_response(empty) == []

    failed = ToolResponse(
        ok=False,
        evidence=[],
        diagnostics=ToolDiagnostics(tool_name="search_pubmed", result_count=0),
        error=A2Error(
            code=A2ErrorCode.UPSTREAM_HTTP_ERROR,
            source="pubmed",
            message="upstream unavailable",
            retryable=True,
        ),
    )
    with pytest.raises(A2ToA3NormalizationError, match="UPSTREAM_HTTP_ERROR"):
        normalizer.normalize_tool_response(failed)


def test_a2_tool_response_contract_rejects_ambiguous_failure() -> None:
    diagnostics = ToolDiagnostics(tool_name="search_pubmed")
    with pytest.raises(ValidationError, match="must carry a structured error"):
        ToolResponse(ok=False, diagnostics=diagnostics)
    with pytest.raises(ValidationError, match="must not carry an error"):
        ToolResponse(
            ok=True,
            diagnostics=diagnostics,
            error=A2Error(code=A2ErrorCode.INTERNAL_ERROR, message="invalid envelope"),
        )


class MustNotCallConnector:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, limit: int = 10) -> list[A2Evidence]:
        del query, limit
        self.calls += 1
        raise AssertionError("live connector must stay disabled")

    def get(self, identifier: str) -> A2Evidence:
        del identifier
        self.calls += 1
        raise AssertionError("live connector must stay disabled")


def test_a2_citation_live_disabled_returns_unknown_without_network(tmp_path: Path) -> None:
    connector = MustNotCallConnector()
    service = A2ToolService(
        store=SQLiteStore(tmp_path / "a2.sqlite3"),
        pubmed=connector,
        europe_pmc=connector,
        clinical_trials=connector,
        guidelines=connector,
    )
    response = service.validate_citation("PMID:30491001", allow_live_lookup=False)
    assert response["ok"] is True
    assert response["result"]["status"] == "UNKNOWN"
    assert response["result"]["valid"] is None
    assert connector.calls == 0
