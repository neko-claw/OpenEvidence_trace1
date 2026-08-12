from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from a5.domain.enums import SemanticSupportStatus, VerificationStatus
from a5.domain.models import Claim, EvidenceRecord, SemanticVerificationOutput, TextualSupportAssessment
from a5.ports.structured_output import OpenAICompatibleStructuredTransport
from a5.ports.textual_support import TextualSupportEvaluator


class OpenAICompatibleSemanticEvaluator:
    """Independent structured semantic verifier; UNKNOWN maps to INSUFFICIENT."""

    def __init__(
        self,
        *,
        transport: OpenAICompatibleStructuredTransport,
        model: str,
        prompt_path: Path,
        name: str = "independent_semantic_verifier@0.4.0",
    ) -> None:
        self._transport = transport
        self._model = model
        self._prompt = prompt_path.read_text(encoding="utf-8")
        self._name = name

    def evaluate(self, claim: Claim, evidence: Sequence[EvidenceRecord]) -> TextualSupportAssessment:
        cited_span_ids = set(claim.evidence_span_ids)
        spans = [
            {"span_id": span.span_id, "text": span.text}
            for record in evidence
            for span in record.spans
            if span.span_id in cited_span_ids
        ]
        try:
            response = self._transport.complete(
                model=self._model,
                messages=(
                    {"role": "system", "content": self._prompt},
                    {
                        "role": "user",
                        "content": json.dumps({"claim": claim.text, "cited_spans": spans}, ensure_ascii=False),
                    },
                ),
                response_schema=SemanticVerificationOutput.model_json_schema(),
            )
            output = SemanticVerificationOutput.model_validate(response)
        except Exception:
            return self._insufficient("semantic_transport_or_output_invalid")
        if set(output.used_span_ids) - cited_span_ids:
            return self._insufficient("semantic_span_whitelist_violation")
        if output.status is SemanticSupportStatus.CONTRADICTED:
            return TextualSupportAssessment(
                status=VerificationStatus.CONTRADICTED,
                entailment_score=output.entailment_score,
                method=self._name,
                reason=f"contradicted_claim: {output.reason}",
            )
        if (
            output.status is SemanticSupportStatus.SUPPORTED
            and output.entailment_score is not None
            and output.used_span_ids
        ):
            return TextualSupportAssessment(
                status=VerificationStatus.SUPPORTED,
                entailment_score=output.entailment_score,
                method=self._name,
                reason=f"semantic_support: {output.reason}",
            )
        return self._insufficient(f"semantic_unknown: {output.reason}")

    def _insufficient(self, reason: str) -> TextualSupportAssessment:
        return TextualSupportAssessment(
            status=VerificationStatus.INSUFFICIENT,
            entailment_score=None,
            method=self._name,
            reason=reason,
        )


class CompositeTextualSupportEvaluator:
    """Deterministic checks plus an independent semantic decision."""

    def __init__(
        self,
        deterministic: TextualSupportEvaluator,
        semantic: TextualSupportEvaluator,
        *,
        name: str = "deterministic_plus_independent_semantic@0.4.0",
    ) -> None:
        self._deterministic = deterministic
        self._semantic = semantic
        self._name = name

    def evaluate(self, claim: Claim, evidence: Sequence[EvidenceRecord]) -> TextualSupportAssessment:
        deterministic = self._deterministic.evaluate(claim, evidence)
        semantic = self._semantic.evaluate(claim, evidence)
        if VerificationStatus.CONTRADICTED in {deterministic.status, semantic.status}:
            status = VerificationStatus.CONTRADICTED
            score = semantic.entailment_score
        elif semantic.status is VerificationStatus.SUPPORTED:
            status = VerificationStatus.SUPPORTED
            score = semantic.entailment_score
        else:
            status = VerificationStatus.INSUFFICIENT
            score = None
        return TextualSupportAssessment(
            status=status,
            entailment_score=score,
            method=self._name,
            reason=f"{deterministic.reason}; {semantic.reason}",
        )
