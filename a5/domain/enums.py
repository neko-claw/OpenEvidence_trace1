from __future__ import annotations

from enum import StrEnum


class Decision(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    REFUSE = "REFUSE"


class WorkflowState(StrEnum):
    CLASSIFY = "CLASSIFY"
    PLAN = "PLAN"
    SELECT_SKILL = "SELECT_SKILL"
    RETRIEVE = "RETRIEVE"
    CHECK_EVIDENCE = "CHECK_EVIDENCE"
    GENERATE_CLAIMS = "GENERATE_CLAIMS"
    VERIFY_CLAIMS = "VERIFY_CLAIMS"
    FINALIZE = "FINALIZE"
    END = "END"


class ClaimCriticality(StrEnum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    CONTEXT = "context"


class VerificationStatus(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT = "insufficient"


class SafetyStatus(StrEnum):
    ALLOWED = "allowed"
    REFUSED = "refused"
