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
    GENERATE_CLAIMS = "GENERATE_CLAIMS"
    CLAIM_SPLITTER = "CLAIM_SPLITTER"
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
