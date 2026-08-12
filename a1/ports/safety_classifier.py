from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from a1.models import SafetyPolicyInput


class SafetyClassificationRequest(BaseModel):
    """Minimal text-classification request owned by A1.

    The port intentionally contains no medical classification rules. A future
    A1 implementation may use deterministic rules, a reviewed model, or a
    human-confirmed classifier while the A5 adapter remains unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


@runtime_checkable
class SafetySignalClassifier(Protocol):
    """Convert question text into the frozen normalized Gate0 signals."""

    def classify(
        self, request: SafetyClassificationRequest
    ) -> SafetyPolicyInput | Mapping[str, object]: ...
