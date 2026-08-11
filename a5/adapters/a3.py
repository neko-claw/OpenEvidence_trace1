from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from a3.domain.models import (
    A3_CONTRACT_VERSION,
    Chunk,
    Evidence,
    EvidenceSpan,
    IndexManifest,
    canonical_hash,
)
from a5.domain.models import EvidenceRecord, EvidenceSpan as A5EvidenceSpan, StrictModel


class A3AdapterDiagnostics(StrictModel):
    a3_contract_version: str
    evidence_schema_version: str
    chunk_schema_version: str
    span_schema_version: str
    search_hit_schema_version: str
    manifest_schema_version: str
    config_schema_version: str
    corpus_version: str
    index_version: str
    chunk_policy_version: str
    bm25_tokenizer_version: str
    embedding_provider: str
    embedding_model: str
    embedding_revision: str | None
    embedding_source_kind: str
    wiki_builder_version: str
    selected_chunk_ids: list[str]
    selected_span_ids: list[str]
    adapter_reason_codes: list[str]
    runtime_config_snapshot: dict[str, Any]
    runtime_config_hash: str


@dataclass(frozen=True)
class A3Adaptation:
    evidence: EvidenceRecord
    diagnostics: A3AdapterDiagnostics


class A3AdapterError(ValueError):
    def __init__(self, reason_codes: Sequence[str]) -> None:
        self.reason_codes = tuple(dict.fromkeys(reason_codes))
        super().__init__("A3 compatibility adapter rejected selection: " + ", ".join(self.reason_codes))


def adapt_a3_selection(evidence: Evidence, selected_chunks: Sequence[Chunk],
                       spans: Sequence[EvidenceSpan], manifest: IndexManifest, *,
                       index_version: str, corpus_version: str,
                       selected_span_ids: Sequence[str] | None = None) -> A3Adaptation:
    """Canonical A3→A5 boundary for chunks already selected by A4.

    This function never consumes ``SearchHit`` and never manufactures an A4
    normalized retrieval score.
    """
    reasons = _evidence_reasons(evidence)
    if manifest.index_version != index_version:
        reasons.append("index_version_mismatch")
    if manifest.corpus_version != corpus_version:
        reasons.append("corpus_version_mismatch")

    chunks = list(selected_chunks)
    if not chunks:
        reasons.append("stale_chunk")
    if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
        reasons.append("stale_chunk")
    by_chunk = {chunk.chunk_id: chunk for chunk in chunks}
    for chunk in chunks:
        if chunk.evidence_id != evidence.id:
            reasons.append("stale_chunk")
        if chunk.evidence_content_hash != evidence.content_hash:
            reasons.append("evidence_hash_mismatch")
        if canonical_hash(chunk.text) != chunk.content_hash:
            reasons.append("chunk_hash_mismatch")
        if evidence.abstract_or_chunk[chunk.char_start:chunk.char_end] != chunk.text:
            reasons.append("stale_chunk")

    span_by_id = {span.span_id: span for span in spans}
    if len(span_by_id) != len(spans):
        reasons.append("stale_span")
    if selected_span_ids is None:
        selected = [span for span in spans
                    if span.evidence_id == evidence.id and span.chunk_id in by_chunk]
    else:
        requested = list(selected_span_ids)
        if len(set(requested)) != len(requested):
            reasons.append("stale_span")
        missing = [span_id for span_id in requested if span_id not in span_by_id]
        if missing:
            reasons.append("stale_span")
        selected = [span_by_id[span_id] for span_id in requested if span_id in span_by_id]

    for span in selected:
        chunk = by_chunk.get(span.chunk_id)
        if chunk is None:
            reasons.append("span_not_selected")
            continue
        if span.evidence_id != evidence.id:
            reasons.append("stale_span")
        if span.evidence_content_hash != evidence.content_hash:
            reasons.append("evidence_hash_mismatch")
        if span.chunk_content_hash != chunk.content_hash:
            reasons.append("chunk_hash_mismatch")
        if canonical_hash(span.text) != span.content_hash:
            reasons.append("stale_span")
        if chunk.text[span.char_start:span.char_end] != span.text:
            reasons.append("stale_span")
        if evidence.abstract_or_chunk[span.document_char_start:span.document_char_end] != span.text:
            reasons.append("stale_span")

    if reasons:
        raise A3AdapterError(reasons)

    span_provenance = {span.span_id: {
        "chunk_id": span.chunk_id, "raw_page": span.raw_page, "page": span.page,
        "section": span.section, "char_start": span.char_start, "char_end": span.char_end,
        "offset_scope": span.offset_scope, "document_char_start": span.document_char_start,
        "document_char_end": span.document_char_end, "span_content_hash": span.content_hash,
        "chunk_content_hash": span.chunk_content_hash,
        "evidence_content_hash": span.evidence_content_hash,
    } for span in selected}
    diagnostics = _diagnostics(manifest, chunks, selected)
    metadata: dict[str, Any] = {
        "stable_id": evidence.stable_id, "content_hash": evidence.content_hash,
        "tombstone": evidence.tombstone, "fetched_at": evidence.fetched_at.isoformat()
            if evidence.fetched_at else None,
        "chunk_ids": diagnostics.selected_chunk_ids,
        "span_provenance": span_provenance,
        "provenance": evidence.provenance,
        "a3_adapter_diagnostics": diagnostics.model_dump(mode="json"),
    }
    for key in ("url", "pmid", "doi", "nct_id", "guideline_name"):
        value = getattr(evidence, key)
        if value is not None:
            metadata[key] = value
    record = EvidenceRecord(id=evidence.id, content="\n".join(chunk.text for chunk in chunks),
        source_type=evidence.source_type, title=evidence.title, source_metadata=metadata,
        population=evidence.population, intervention=evidence.intervention,
        comparator=evidence.comparator, outcome=evidence.outcome,
        published_at=evidence.published_at, retrieval_score=None,
        evidence_level=evidence.evidence_level,
        spans=[A5EvidenceSpan(span_id=span.span_id, text=span.text, chunk_id=span.chunk_id,
            page=span.page, section=span.section) for span in selected], mock=evidence.mock)
    return A3Adaptation(evidence=record, diagnostics=diagnostics)


def _evidence_reasons(evidence: Evidence) -> list[str]:
    if evidence.tombstone:
        return ["tombstoned_evidence"]
    if evidence.mock:
        if any((evidence.url, evidence.pmid, evidence.doi, evidence.nct_id, evidence.guideline_name)) \
                or not evidence.provenance.get("fixture"):
            return ["mock_provenance_violation"]
        return []
    has_version = evidence.published_at is not None or bool(evidence.provenance.get("version"))
    has_identifier = any((evidence.pmid, evidence.doi, evidence.nct_id,
                          evidence.guideline_name, evidence.upstream_id))
    if not all((evidence.source_type, evidence.url, evidence.fetched_at,
                evidence.provenance, has_version, has_identifier, evidence.content_hash)):
        return ["missing_provenance"]
    return []


def _diagnostics(manifest: IndexManifest, chunks: Sequence[Chunk],
                 spans: Sequence[EvidenceSpan]) -> A3AdapterDiagnostics:
    return A3AdapterDiagnostics(a3_contract_version=A3_CONTRACT_VERSION,
        evidence_schema_version=manifest.evidence_schema_version,
        chunk_schema_version=manifest.chunk_schema_version,
        span_schema_version=manifest.span_schema_version,
        search_hit_schema_version=manifest.search_hit_schema_version,
        manifest_schema_version=manifest.manifest_schema_version,
        config_schema_version=manifest.config_schema_version,
        corpus_version=manifest.corpus_version, index_version=manifest.index_version,
        chunk_policy_version=manifest.chunk_policy_version,
        bm25_tokenizer_version=manifest.bm25_tokenizer_version,
        embedding_provider=manifest.embedding_provider, embedding_model=manifest.embedding_model,
        embedding_revision=manifest.embedding_revision,
        embedding_source_kind=manifest.embedding_source_kind,
        wiki_builder_version=manifest.wiki_builder_version,
        selected_chunk_ids=[chunk.chunk_id for chunk in chunks],
        selected_span_ids=[span.span_id for span in spans], adapter_reason_codes=[],
        runtime_config_snapshot=manifest.runtime_effective_config,
        runtime_config_hash=canonical_hash(manifest.runtime_effective_config))
