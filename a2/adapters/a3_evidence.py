from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import ValidationError

from a2.models.evidence import A2Evidence
from a2.models.tool_response import ToolResponse


class A2ToA3NormalizationError(ValueError):
    """The A2 envelope cannot safely cross the frozen A3 boundary."""


class A2ToA3Normalizer:
    """Map ``a2-evidence-v1`` into A3 Evidence v0.3 input fields.

    This adapter deliberately does not create chunks, spans, PICO values,
    evidence levels, trust labels, or semantic verification decisions. A2's
    content hash and source metadata are retained as provenance; A3 remains the
    owner of its own canonical hash, chunking, span and index contracts.
    """

    def normalize(self, record: A2Evidence | Mapping[str, Any]) -> dict[str, Any]:
        try:
            item = record if isinstance(record, A2Evidence) else A2Evidence.model_validate(record)
        except (TypeError, ValueError, ValidationError) as exc:
            raise A2ToA3NormalizationError(
                f"invalid a2-evidence-v1 record: {type(exc).__name__}"
            ) from exc

        provenance: dict[str, Any] = {
            "a2_schema_version": item.schema_version,
            "a2_content_hash": item.content_hash,
            "a2_source_type": item.source_type.value,
            "a2_fetched_at": item.fetched_at.isoformat(),
            "a2_source_metadata": dict(item.source_metadata),
        }
        if item.mock:
            provenance["fixture"] = True

        return {
            "id": item.id,
            "source_type": item.source_type.value,
            "title": item.title,
            "abstract_or_chunk": item.abstract_or_chunk,
            "authors": list(item.authors),
            "published_at": item.published_at,
            "url": item.url,
            "pmid": item.pmid,
            "doi": item.doi,
            "nct_id": item.nct_id,
            "guideline_name": item.guideline_name,
            "upstream_id": item.id,
            "page": str(item.page) if item.page is not None else None,
            "section": None,
            "evidence_level": item.evidence_level,
            "population": item.population,
            "intervention": item.intervention,
            "comparator": item.comparator,
            "outcome": item.outcome,
            "fetched_at": item.fetched_at,
            "provenance": provenance,
            "mock": item.mock,
            "tombstone": False,
        }

    def normalize_many(
        self, records: Iterable[A2Evidence | Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        return [self.normalize(record) for record in records]

    def normalize_tool_response(
        self, response: ToolResponse | Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        try:
            envelope = (
                response
                if isinstance(response, ToolResponse)
                else ToolResponse.model_validate(response)
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise A2ToA3NormalizationError(
                f"invalid A2 ToolResponse: {type(exc).__name__}"
            ) from exc
        if not envelope.ok:
            code = envelope.error.code.value if envelope.error is not None else "UNKNOWN"
            raise A2ToA3NormalizationError(f"A2 tool failed: {code}")
        return self.normalize_many(envelope.evidence)
