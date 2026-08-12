from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

from a5.domain.models import AgentPlan, Claim, ClaimGenerationOutput, EvidenceRecord, Question
from a5.ports.structured_output import OpenAICompatibleStructuredTransport


class ClaimGenerationError(RuntimeError):
    """Fail-closed structured generation or whitelist failure."""


class OpenAICompatibleClaimGenerator:
    """Production adapter for an injected OpenAI-compatible JSON transport."""

    _external_reference = re.compile(
        r"(?:https?://|www\.|\bPMID\s*:?\s*\d+\b|\bNCT\d{8}\b|"
        r"\b10\.\d{4,9}/\S+|\bGUIDELINE\s*:)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        transport: OpenAICompatibleStructuredTransport,
        model: str,
        prompt_path: Path,
    ) -> None:
        self._transport = transport
        self._model = model
        self._prompt = prompt_path.read_text(encoding="utf-8")

    def generate(
        self,
        question: Question,
        evidence: Sequence[EvidenceRecord],
        plan: AgentPlan,
        run_id: str,
    ) -> list[Claim]:
        allowed_evidence = {record.id: record for record in evidence}
        span_owner = {
            span.span_id: record.id for record in evidence for span in record.spans
        }
        response = self._transport.complete(
            model=self._model,
            messages=(
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": self._input_json(question, evidence, plan)},
            ),
            response_schema=ClaimGenerationOutput.model_json_schema(),
        )
        try:
            generated = ClaimGenerationOutput.model_validate(response)
        except Exception as exc:
            raise ClaimGenerationError("structured_output_invalid") from exc
        claim_ids: set[str] = set()
        claims: list[Claim] = []
        for payload in generated.claims:
            if payload.claim_id in claim_ids:
                raise ClaimGenerationError("duplicate_claim_id")
            claim_ids.add(payload.claim_id)
            illegal_evidence = set(payload.evidence_ids) - set(allowed_evidence)
            illegal_spans = set(payload.evidence_span_ids) - set(span_owner)
            wrong_owner = {
                span_id
                for span_id in payload.evidence_span_ids
                if span_id in span_owner and span_owner[span_id] not in payload.evidence_ids
            }
            if illegal_evidence or illegal_spans or wrong_owner:
                raise ClaimGenerationError("generation_whitelist_violation")
            if self._external_reference.search(payload.text):
                raise ClaimGenerationError("generated_external_reference")
            claims.append(Claim(run_id=run_id, **payload.model_dump()))
        return claims

    @staticmethod
    def _input_json(
        question: Question,
        evidence: Sequence[EvidenceRecord],
        plan: AgentPlan,
    ) -> str:
        payload = {
            "question": question.text,
            "question_type": plan.question_type,
            "allowed_evidence_ids": [record.id for record in evidence],
            "allowed_span_ids": [span.span_id for record in evidence for span in record.spans],
            "evidence": [
                {
                    "id": record.id,
                    "title": record.title,
                    "content": record.content,
                    "population": record.population,
                    "intervention": record.intervention,
                    "comparator": record.comparator,
                    "outcome": record.outcome,
                    "published_at": record.published_at.isoformat() if record.published_at else None,
                    "spans": [
                        {"span_id": span.span_id, "text": span.text}
                        for span in record.spans
                    ],
                }
                for record in evidence
            ],
        }
        return json.dumps(payload, ensure_ascii=False)
