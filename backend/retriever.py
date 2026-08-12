from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from a3.domain.models import Evidence, EvidenceSpan, IndexManifest
from a3.indexing.bm25 import BM25Index as A3BM25Index
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from a3.indexing.embeddings import EmbeddingProvider
from a3.indexing.vector import ChromaVectorIndex, vector_text
from a3.indexing.versions import create_manifest
from a5.adapters.a4_evidence_retriever import A4EvidenceRetrieverAdapter
from a5.domain.models import Question, RetrievalRequest, RetrievalResult, SearchPlan
from retrieval.a3_pool_adapter import build_initial_pool_from_a3_hits
from retrieval.config import RetrievalConfig
from retrieval.models import Query, RetrievalCondition, ScoredChunk
from retrieval.ports import CalibratedQualityScorer, ClaimEvidenceSupportGate
from retrieval.service import RetrievalService

from backend.config import BackendConfig, load_backend_config
from backend.source import A2EvidenceSource


class _UnusedLexicalSearch:
    """Constructor dependency for a service driven by a frozen A3 pool."""

    def search(self, _query: str, _k: int) -> list[ScoredChunk]:
        raise AssertionError("A3 frozen-pool composition must not invoke A4 retrieval")


class _FrozenPoolService:
    def __init__(
        self,
        service: RetrievalService,
        pool: object,
        condition: RetrievalCondition,
    ) -> None:
        self._service = service
        self._pool = pool
        self._condition = condition

    def search(self, query: Query):  # SearchResult annotation would add only noise here.
        return self._service.search_from_pool(query, self._pool, self._condition)


class CoordinatedEvidenceRetriever:
    """A5 Port implementation that coordinates A2 -> A3 -> A4.

    A2 owns source tools, A3 owns evidence/chunk/span/embedding/index contracts,
    A4 owns candidate fusion and reranking, and A5 remains the only caller that
    decides tool budget, evidence sufficiency, verification, and release.
    """

    def __init__(
        self,
        source: A2EvidenceSource,
        embedding_provider: EmbeddingProvider,
        *,
        index_root: str | Path,
        backend_config: BackendConfig | None = None,
        retrieval_config: RetrievalConfig | None = None,
        quality_scorer: CalibratedQualityScorer | None = None,
        cross_encoder: Any | None = None,
        support_gate: ClaimEvidenceSupportGate | None = None,
    ) -> None:
        self._source = source
        self._embedding = embedding_provider
        self._index_root = Path(index_root)
        self._backend = backend_config or load_backend_config()
        self._retrieval = retrieval_config or RetrievalConfig()
        self._quality_scorer = quality_scorer
        self._cross_encoder = cross_encoder
        self._support_gate = support_gate
        self.call_count = 0

    def retrieve(
        self,
        question: Question,
        plan: SearchPlan,
        request: RetrievalRequest,
    ) -> RetrievalResult:
        self.call_count += 1
        batch = self._source.acquire(
            queries=list(plan.queries),
            source_alias=request.source_type,
            tool_call_index=request.tool_call_index,
        )
        if batch.error_code or not batch.evidence:
            return RetrievalResult(
                evidence=[],
                tool_name=batch.tool_name or "unsupported_source_alias",
                diagnostics={
                    **batch.diagnostics,
                    "pipeline": ["A2_MCP"],
                    "error_code": batch.error_code,
                },
            )
        try:
            return self._retrieve_batch(question, plan, request, batch)
        except Exception as exc:
            return RetrievalResult(
                evidence=[],
                tool_name=batch.tool_name or "a2_mcp",
                diagnostics={
                    **batch.diagnostics,
                    "pipeline": ["A2_MCP", "A3_INDEX", "A4_RETRIEVAL"],
                    "error_code": "A3_A4_PIPELINE_ERROR",
                    "safe_error": f"{type(exc).__name__}: evidence indexing or retrieval unavailable",
                },
            )

    def _retrieve_batch(self, question, plan, request, batch) -> RetrievalResult:
        evidence = list(batch.evidence)
        policy = ChunkPolicy(
            version=self._backend.chunk_policy_version,
            max_chars=self._backend.chunk_max_chars,
            overlap_chars=self._backend.chunk_overlap_chars,
            natural_boundary_ratio=self._backend.chunk_natural_boundary_ratio,
        )
        chunks = []
        spans: list[EvidenceSpan] = []
        for record in evidence:
            record_chunks, record_spans = chunk_evidence(record, policy)
            chunks.extend(record_chunks)
            spans.extend(record_spans)
        manifest = self._manifest(evidence, policy)
        config = replace(
            self._retrieval,
            index_version=manifest.index_version,
            corpus_version=manifest.corpus_version,
        )
        search_text = " ".join([question.text, *plan.queries])
        lexical = A3BM25Index.build(evidence, chunks, spans, manifest)
        lexical_hits = lexical.search(search_text, config.bm25_top_k)

        # Each question owns its transient index namespace. Concurrent user
        # requests must never delete or overwrite another run's candidate pool.
        vector_root = self._index_root / question.question_id / f"tool-{request.tool_call_index}"
        vector = ChromaVectorIndex(vector_root, manifest, self._embedding)
        vector.sync(evidence, chunks, spans)
        vector_hits = vector.search(search_text, config.vector_top_k)

        by_evidence = {record.id: record for record in evidence}
        chunk_vectors_list = self._embedding.encode_documents(
            [vector_text(by_evidence[chunk.evidence_id], chunk) for chunk in chunks]
        )
        content_vectors = {
            chunk.chunk_id: values
            for chunk, values in zip(chunks, chunk_vectors_list, strict=True)
        }
        pool_query = Query(
            query_id=question.question_id,
            text=question.text,
            as_of_date=self._as_of_date(question),
            source_types=tuple(sorted({item.source_type for item in evidence})),
        )
        pool = build_initial_pool_from_a3_hits(
            pool_query,
            lexical_hits,
            vector_hits,
            config,
            content_vectors=content_vectors,
        )
        service = RetrievalService(
            _UnusedLexicalSearch(),
            None,
            None,
            config,
            cross_encoder=self._cross_encoder,
            support_gate=self._support_gate,
            quality_scorer=self._quality_scorer,
        )
        frozen = _FrozenPoolService(
            service,
            pool,
            RetrievalCondition(self._backend.default_retrieval_condition),
        )
        spans_by_chunk: dict[str, list[EvidenceSpan]] = {}
        for span in spans:
            spans_by_chunk.setdefault(span.chunk_id, []).append(span)
        adapted = A4EvidenceRetrieverAdapter(
            frozen,
            config,
            tool_name="a2_mcp_a3_index_a4_rerank",
            span_provider=lambda chunk_id: spans_by_chunk.get(chunk_id, []),
        ).retrieve(question, plan, request)
        enriched = [self._enrich(record, by_evidence) for record in adapted.evidence]
        diagnostics = {
            **adapted.diagnostics,
            "pipeline": ["A2_MCP", "A2_TO_A3", "A3_INDEX", "A4_RETRIEVAL"],
            "a2": batch.diagnostics,
            "a3": {
                "index_version": manifest.index_version,
                "corpus_version": manifest.corpus_version,
                "chunk_policy_version": manifest.chunk_policy_version,
                "embedding_provider": manifest.embedding_provider,
                "embedding_model": manifest.embedding_model,
                "embedding_revision": manifest.embedding_revision,
                "evidence_count": len(evidence),
                "chunk_count": len(chunks),
                "span_count": len(spans),
            },
            "retrieval_condition": self._backend.default_retrieval_condition,
            "initial_candidate_pool_hash": pool.pool_hash,
        }
        return adapted.model_copy(update={"evidence": enriched, "diagnostics": diagnostics})

    def _manifest(self, evidence: list[Evidence], policy: ChunkPolicy) -> IndexManifest:
        snapshot = self._backend.snapshot()
        effective = {
            "chunk_policy": policy.as_dict(),
            "bm25": {"tokenizer_version": "a3-bm25-v0.3"},
            "embedding": {
                "provider": type(self._embedding).__name__,
                "model": self._embedding.model_id,
                "revision": self._embedding.revision,
                "source_kind": self._embedding.source_kind,
                "mode": "dense",
            },
            "vector": {"distance": "cosine"},
            "wiki": {"builder_version": "not_used_in_dynamic_tool_batch"},
        }
        return create_manifest(
            evidence=evidence,
            chunk_policy_version=policy.version,
            chunk_policy=policy.as_dict(),
            embedding_provider=type(self._embedding).__name__,
            embedding_model=self._embedding.model_id,
            embedding_revision=self._embedding.revision,
            embedding_source_kind=self._embedding.source_kind,
            embedding_mode="dense",
            vector_distance="cosine",
            bm25_tokenizer_version="a3-bm25-v0.3",
            wiki_builder_version="not_used_in_dynamic_tool_batch",
            config_schema_version=self._backend.config_version,
            requested_config=snapshot,
            runtime_effective_config=effective,
        )

    @staticmethod
    def _enrich(record, evidence_by_id: dict[str, Evidence]):
        source_id = str(record.source_metadata.get("evidence_id") or "")
        source = evidence_by_id.get(source_id)
        if source is None:
            return record
        metadata = {
            **record.source_metadata,
            "stable_id": source.stable_id,
            "url": source.url,
            "fetched_at": source.fetched_at.isoformat() if source.fetched_at else None,
            "content_hash": source.content_hash,
            "tombstone": source.tombstone,
            "source_integrity": "a4_a3_provenance_validated",
            "a2_provenance": source.provenance,
        }
        for name in ("pmid", "doi", "nct_id", "guideline_name"):
            value = getattr(source, name)
            if value is not None:
                metadata[name] = value
        return record.model_copy(update={"source_metadata": metadata})

    @staticmethod
    def _as_of_date(question: Question) -> date:
        value = question.metadata.get("as_of_date")
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        return date.today()
