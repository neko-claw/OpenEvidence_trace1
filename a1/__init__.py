"""A1 product, safety, and evaluation contracts."""

from a1.models import (
    Decision,
    RetrievalTerminationInput,
    RetrievalTerminationOutput,
    SafetyDecision,
    SafetyPolicyInput,
    SafetyPolicyOutput,
    TerminationAction,
)
from a1.policy import ReferenceSafetyPolicy, evaluate_retrieval_termination

__all__ = [
    "Decision",
    "ReferenceSafetyPolicy",
    "RetrievalTerminationInput",
    "RetrievalTerminationOutput",
    "SafetyDecision",
    "SafetyPolicyInput",
    "SafetyPolicyOutput",
    "TerminationAction",
    "evaluate_retrieval_termination",
]
