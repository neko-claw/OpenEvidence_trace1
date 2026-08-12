from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from a1.models import SafetyPolicyInput, SpecialPopulation, TopicScope
from a1.ports.safety_classifier import SafetyClassificationRequest


@runtime_checkable
class StructuredSafetyTransport(Protocol):
    """Injected structured-output transport; credentials and SDK stay outside A1."""

    def complete(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        response_schema: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]: ...


class SafetySignalPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: TopicScope
    acute_emergency: bool
    personal_diagnosis: bool
    personalized_prescribing_or_dose_change: bool
    prompt_injection_or_fabricated_reference: bool
    identifiable_personal_data: bool
    special_population: SpecialPopulation
    confidence: float = Field(ge=0.0, le=1.0)


class SafetyClassifierError(RuntimeError):
    """Classifier failure that callers must convert to UNKNOWN."""


class StructuredSafetySignalClassifier:
    """Strict free-text classifier over an injected structured transport.

    This adapter contains no keyword fallback. Malformed output, low confidence,
    transport errors and incomplete/UNKNOWN predictions all raise a typed error;
    A1's A5 adapter converts every such failure to UNKNOWN and Gate0 refuses.
    """

    def __init__(
        self,
        *,
        transport: StructuredSafetyTransport,
        model: str,
        prompt_path: str | Path,
        version: str = "a1-safety-classifier-v0.1.0",
        min_confidence: float = 0.85,
        timeout_seconds: float = 5.0,
    ) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0,1]")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.version = version
        self._transport = transport
        self._model = model
        self._prompt = Path(prompt_path).read_text(encoding="utf-8")
        self._min_confidence = min_confidence
        self._timeout_seconds = timeout_seconds

    def classify(self, request: SafetyClassificationRequest) -> SafetyPolicyInput:
        try:
            raw = self._transport.complete(
                model=self._model,
                messages=(
                    {"role": "system", "content": self._prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"question_id": request.question_id, "text": request.text},
                            ensure_ascii=False,
                        ),
                    },
                ),
                response_schema=SafetySignalPrediction.model_json_schema(),
                timeout_seconds=self._timeout_seconds,
            )
            prediction = SafetySignalPrediction.model_validate(raw)
        except Exception as exc:
            raise SafetyClassifierError("classifier_output_unknown") from exc
        if prediction.confidence < self._min_confidence:
            raise SafetyClassifierError("classifier_low_confidence")
        if prediction.topic is TopicScope.UNKNOWN:
            raise SafetyClassifierError("classifier_topic_unknown")
        if prediction.special_population is SpecialPopulation.UNKNOWN:
            raise SafetyClassifierError("classifier_population_unknown")
        return SafetyPolicyInput(
            question_id=request.question_id,
            **prediction.model_dump(exclude={"confidence"}),
        )
