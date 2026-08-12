from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Decision(StrEnum):
    """Top-level publication outcome shared with A5."""

    PASS = "PASS"
    WARN = "WARN"
    REFUSE = "REFUSE"


class SafetyDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class TerminationAction(StrEnum):
    CONTINUE = "CONTINUE"
    RETRY = "RETRY"
    WARN = "WARN"
    REFUSE = "REFUSE"


class TopicScope(StrEnum):
    HYPERTENSION = "hypertension"
    DYSLIPIDEMIA = "dyslipidemia"
    CARDIOVASCULAR = "cardiovascular"
    CEREBROVASCULAR = "cerebrovascular"
    DIABETES = "diabetes"
    OTHER = "other"
    UNKNOWN = "unknown"


class SpecialPopulation(StrEnum):
    NONE = "none"
    PREGNANCY = "pregnancy"
    PEDIATRIC = "pediatric"
    OTHER = "other"
    UNKNOWN = "unknown"


class SafetyPolicyInput(StrictModel):
    """Normalized Gate0 signals.

    The reference implementation deliberately does not infer these signals from
    free text. A future A1 classifier/adapter must provide them. Missing signals
    stay ``None`` and therefore fail closed.
    """

    question_id: str = Field(min_length=1)
    topic: TopicScope = TopicScope.UNKNOWN
    acute_emergency: bool | None = None
    personal_diagnosis: bool | None = None
    personalized_prescribing_or_dose_change: bool | None = None
    prompt_injection_or_fabricated_reference: bool | None = None
    identifiable_personal_data: bool | None = None
    special_population: SpecialPopulation = SpecialPopulation.UNKNOWN


class SafetyPolicyOutput(StrictModel):
    decision: SafetyDecision
    policy_version: str = Field(pattern=r"^a1-safety-v\d+\.\d+$")
    reason_codes: list[str] = Field(min_length=1)
    matched_rules: list[str] = Field(default_factory=list)
    termination_action: TerminationAction
    user_message_key: str = Field(min_length=1)


class RetrievalTerminationInput(StrictModel):
    evidence_sufficient: bool | None
    tool_budget_exhausted: bool
    evidence_present: bool
    required_source_type_missing: bool = False
    unresolved_conflict: bool = False


class RetrievalTerminationOutput(StrictModel):
    action: TerminationAction
    decision: Decision | None = None
    reason_codes: list[str] = Field(min_length=1)


class BudgetContract(StrictModel):
    retrieval_tool_calls_min: int = Field(ge=0)
    retrieval_tool_calls_max: int = Field(ge=1)
    total_tool_calls_max: int = Field(ge=1)
    query_rewrite_max: int = Field(ge=0)
    generation_attempts_max: int = Field(ge=1)
    verifier_attempts_max: int = Field(ge=1)


class SafetyContract(StrictModel):
    policy_version: str = Field(pattern=r"^a1-safety-v\d+\.\d+$")
    default_decision: SafetyDecision
    unknown_action: TerminationAction
    deny_action: TerminationAction
    allow_action: TerminationAction
    input_schema: str
    output_schema: str


class RetrievalContract(StrictModel):
    input_schema: str
    output_schema: str
    precedence: list[str] = Field(min_length=1)


class ReleaseContract(StrictModel):
    decisions: list[Decision]
    reason_code_field: str


class TerminationPolicyAsset(StrictModel):
    version: str = Field(pattern=r"^agent-termination-v\d+\.\d+$")
    status: str
    frozen_at: str
    budgets: BudgetContract
    safety: SafetyContract
    retrieval: RetrievalContract
    release: ReleaseContract
    reason_codes: dict[str, str]
