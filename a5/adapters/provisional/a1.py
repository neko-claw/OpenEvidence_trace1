from __future__ import annotations

from datetime import date
from collections.abc import Callable, Mapping
from typing import Literal

from pydantic import Field, field_validator

from a5.domain.enums import SafetyDecision
from a5.domain.models import Question, SafetyAssessment, StrictModel
from a5.ports.a1_policy_evaluator import A1PolicyEvaluator
from a5.runtime_config import IntegrationsConfig, load_runtime_config


A1QuestionType = Literal[
    "stable_mechanism",
    "guideline_treatment",
    "latest_research_trial",
    "insufficient_conflict_out_of_scope",
]


class A1CandidateSource(StrictModel):
    source_type: Literal[
        "pubmed",
        "clinicaltrials",
        "guideline",
        "official_health",
        "search_route",
        "safety_policy",
    ]
    stable_id: str
    url: str | None = None
    role: Literal["candidate_gold", "candidate_support", "candidate_conflict", "routing_only"]
    verification_status: Literal[
        "source_exists_a1", "pending_a2_ingestion", "pending_b2_gold_review"
    ]
    published_at: date | None = None
    source_version: str | None = None


class A1SourceProvenance(StrictModel):
    origin: Literal["a1_blueprint", "teacher", "guideline", "literature", "public_benchmark"]
    authoring_method: str
    candidate_sources: list[A1CandidateSource]


class A1QuestionPayload(StrictModel):
    """Runtime mirror of A1 Question v0.2 for drift detection, not ownership."""

    id: str = Field(pattern=r"^(DEV|TEST|STRESS|EXTERNAL|RESERVE)-(HTN|LIP)-[0-9]{2,3}$")
    split: Literal["DEV", "TEST", "STRESS", "EXTERNAL", "RESERVE"]
    dataset_pack: str = Field(pattern=r"^openevidence-(dev|test|stress|external|reserve)-v[0-9]+\.[0-9]+$")
    topic: Literal["hypertension", "dyslipidemia"]
    difficulty: Literal["easy", "medium", "hard"]
    language: Literal["zh-CN", "en"]
    question: str = Field(min_length=8)
    question_type: A1QuestionType
    answerable: bool
    as_of_date: date
    source_provenance: A1SourceProvenance
    source_group_id: str = Field(pattern=r"^SG-(DEV|TEST|STRESS|EXTERNAL|RESERVE)-(HTN|LIP)-[0-9]{2,3}$")
    gold_source_ids: list[str]
    rubric_version: str = Field(pattern=r"^rubric-(candidate|frozen)-v[0-9]+\.[0-9]+$")
    expected_source_types: list[
        Literal[
            "pubmed_review",
            "pubmed_trial",
            "clinicaltrials_record",
            "current_guideline",
            "official_health_page",
            "none_required_for_scope_refusal",
        ]
    ] = Field(min_length=1)
    critical_answer_points: list[str] = Field(min_length=1)
    contraindicating_evidence: list[str]
    penalty_points: list[str] = Field(min_length=1)
    evidence_gap_label: Literal[
        "none_expected",
        "results_not_posted",
        "guideline_conflict",
        "patient_specific_data_missing",
        "acute_care_out_of_scope",
        "malicious_or_fabricated_reference",
    ]
    review_status: Literal[
        "A1_COMPLETE_B2_GOLD_PENDING", "B2_REVIEWED", "B2_ADJUDICATED", "RETIRED"
    ]

    @field_validator("gold_source_ids", "expected_source_types")
    @classmethod
    def unique_items(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("A1 contract arrays marked uniqueItems must be unique")
        return value


class A1SafetyVerdict(StrictModel):
    decision: SafetyDecision
    reason_codes: list[str] = Field(min_length=1)
    matched_rules: list[str] = Field(default_factory=list)
    termination_action: Literal["CONTINUE", "RETRY", "WARN", "REFUSE"]
    user_message_key: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)


class A1QuestionAdapter:
    def __init__(self, config: IntegrationsConfig | None = None) -> None:
        self._config = config or load_runtime_config().integrations

    def adapt(
        self,
        payload: A1QuestionPayload | dict[str, object],
        *,
        safety_signals: dict[str, object] | None = None,
    ) -> Question:
        item = payload if isinstance(payload, A1QuestionPayload) else A1QuestionPayload.model_validate(payload)
        return Question(
            question_id=item.id,
            text=item.question,
            metadata={
                "a1_contract_validated": True,
                "a1_contract_version": self._config.a1.contract_version,
                "question_type": item.question_type,
                "topic": item.topic,
                "language": item.language,
                "as_of_date": item.as_of_date.isoformat(),
                "answerable": item.answerable,
                "expected_source_types": list(item.expected_source_types),
                "evidence_gap_label": item.evidence_gap_label,
                "dataset_pack": item.dataset_pack,
                "split": item.split,
                "review_status": item.review_status,
                "a1_safety_signals": safety_signals,
            },
        )


class A1SafetyPolicyAdapter:
    """Convert an injected A1 decision to A5 Gate0; failures become UNKNOWN."""

    def __init__(
        self,
        evaluator: A1PolicyEvaluator,
        config: IntegrationsConfig | None = None,
        *,
        input_factory: Callable[[Mapping[str, object]], object] = dict,
    ) -> None:
        self._evaluator = evaluator
        self._config = config or load_runtime_config().integrations
        self._input_factory = input_factory

    def assess(self, question: Question) -> SafetyAssessment:
        try:
            raw_signals = question.metadata.get("a1_safety_signals")
            if not isinstance(raw_signals, dict):
                raise ValueError("a1_safety_signals missing")
            payload = dict(raw_signals)
            payload.setdefault("question_id", question.question_id)
            raw = self._evaluator.assess(self._input_factory(payload))
            verdict = raw if isinstance(raw, A1SafetyVerdict) else A1SafetyVerdict.model_validate(raw)
            expected_action = (
                "CONTINUE" if verdict.decision is SafetyDecision.ALLOW else "REFUSE"
            )
            if verdict.termination_action != expected_action:
                raise ValueError("A1 decision and termination_action disagree")
        except Exception as error:
            return SafetyAssessment(
                decision=SafetyDecision.UNKNOWN,
                reason=f"safety_unknown: A1 evaluator unavailable or invalid ({type(error).__name__})",
                policy_version=f"a1-adapter@{self._config.a1.contract_version}",
            )
        return SafetyAssessment(
            decision=verdict.decision,
            reason="; ".join(verdict.reason_codes),
            policy_version=verdict.policy_version,
        )
