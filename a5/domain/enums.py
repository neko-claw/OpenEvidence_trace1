from __future__ import annotations

from enum import StrEnum


class Decision(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    REFUSE = "REFUSE"


class WorkflowState(StrEnum):
    START = "START"
    GATE0 = "GATE0"
    CLASSIFY = "CLASSIFY"
    SELECT_SKILL = "SELECT_SKILL"
    PLAN = "PLAN"
    RETRIEVE = "RETRIEVE"
    GATE1 = "GATE1"
    GATE2 = "GATE2"
    SUMMARIZE_EVIDENCE = "SUMMARIZE_EVIDENCE"
    GATE3 = "GATE3"
    GENERATE_CLAIMS = "GENERATE_CLAIMS"
    CLAIM_SPLITTER = "CLAIM_SPLITTER"
    GATE4 = "GATE4"
    AUDIT_CITATIONS = "AUDIT_CITATIONS"
    GATE5 = "GATE5"
    GATE6 = "GATE6"
    FINALIZE = "FINALIZE"
    END = "END"


class EventType(StrEnum):
    STATE = "state"
    GATE = "gate"
    SKILL = "skill"
    TOOL = "tool"
    GENERATION = "generation"
    DECISION = "decision"
    ERROR = "error"


class ClaimCriticality(StrEnum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    CONTEXT = "context"


class UncertaintyLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"


class SafetyDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class MatchStatus(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


class SufficiencyStatus(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTED = "CONFLICTED"


class RecommendedAction(StrEnum):
    CONTINUE = "CONTINUE"
    RETRY = "RETRY"
    WARN = "WARN"
    REFUSE = "REFUSE"


class FreshnessState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    NOT_REQUIRED = "NOT_REQUIRED"


class EvidenceIntegrityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class RetrievalScoreKind(StrEnum):
    QUALITY = "QUALITY"
    RANKING = "RANKING"
    UNKNOWN = "UNKNOWN"


class RetrievalScoreScope(StrEnum):
    CROSS_QUERY = "CROSS_QUERY"
    QUERY_LOCAL = "QUERY_LOCAL"
    UNKNOWN = "UNKNOWN"


class GenerationConstraintStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class UIReasonCode(StrEnum):
    SAFETY_DENIED = "safety_denied"
    INTEGRITY_REJECTED = "integrity_rejected"
    RETRIEVAL_INSUFFICIENT = "retrieval_insufficient"
    RETRIEVAL_CONFLICT = "retrieval_conflict"
    BUDGET_EXHAUSTED = "budget_exhausted"
    GENERATION_REJECTED = "generation_rejected"
    ILLEGAL_CITATION = "illegal_citation"
    MISSING_SPAN = "missing_span"
    PICO_MISMATCH = "pico_mismatch"
    TIME_MISMATCH = "time_mismatch"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    CONTRADICTED_CLAIM = "contradicted_claim"
    HIGH_UNCERTAINTY = "high_uncertainty"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    INTERNAL_ERROR = "internal_error"


class SemanticSupportStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"
