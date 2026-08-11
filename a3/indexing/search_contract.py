from __future__ import annotations

from collections.abc import Sequence

from a3.domain.models import EvidenceSpan, IndexManifest, SearchSpanRef


def manifest_search_fields(manifest: IndexManifest) -> dict[str, object]:
    return {
        "corpus_version": manifest.corpus_version,
        "index_version": manifest.index_version,
        "chunk_policy_version": manifest.chunk_policy_version,
        "bm25_tokenizer_version": manifest.bm25_tokenizer_version,
        "embedding_provider": manifest.embedding_provider,
        "embedding_model": manifest.embedding_model,
        "embedding_revision": manifest.embedding_revision,
        "embedding_source_kind": manifest.embedding_source_kind,
        "wiki_builder_version": manifest.wiki_builder_version,
        "config_schema_version": manifest.config_schema_version,
    }


def span_refs_for_chunk(spans: Sequence[EvidenceSpan], chunk_id: str) -> list[SearchSpanRef]:
    return [SearchSpanRef(span_id=span.span_id, chunk_id=span.chunk_id, text=span.text,
        char_start=span.char_start, char_end=span.char_end, offset_scope=span.offset_scope,
        document_char_start=span.document_char_start,
        document_char_end=span.document_char_end, page=span.page, raw_page=span.raw_page,
        section=span.section, span_content_hash=span.content_hash,
        chunk_content_hash=span.chunk_content_hash,
        evidence_content_hash=span.evidence_content_hash)
        for span in spans if span.chunk_id == chunk_id]
