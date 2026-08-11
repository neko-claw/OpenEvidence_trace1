"""A4 evidence retriever for the main project's ``a5.ports`` contract.

``A5EvidenceRetriever`` adapts ``retrieval.RetrievalService`` to the
``a5.ports.EvidenceRetriever`` port (Question / SearchPlan / RetrievalRequest
-> RetrievalResult).  It deliberately performs no answer generation, no
citation verification, and no scope refusal beyond the explicit
``out_of_scope`` hand-off: A5 owns generation, citation audit, and the final
scope gate, and must consume ``RetrievalResult.selected_chunks`` only.
"""

from __future__ import annotations

from dataclasses import replace

from retrieval.models import Query
from retrieval.ports import (
    EvidenceRetriever,
    RetrievalRequest,
    RetrievalResult,
    question_to_query,
    result_to_retrieval_result,
)


class A5EvidenceRetriever:
    """Adapter: ``a5.ports.EvidenceRetriever`` -> ``RetrievalService``.

    ``search`` runs the A4 pipeline and returns a port payload.  A direct A4
    caller can also use ``search_query`` to obtain the native ``SearchResult``
    (e.g. for JSONL run records); the port payload is derived from it, so the
    two views never diverge.
    """

    def __init__(self, service) -> None:
        if not callable(getattr(service, "search", None)):
            raise ValueError("service must provide a callable search method")
        self._service = service

    @property
    def service(self):
        return self._service

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """Port entry point: run retrieval and return the A5 hand-off payload."""
        if not isinstance(request, RetrievalRequest):
            raise ValueError("request must be a RetrievalRequest")
        query = question_to_query(request.question, request.plan)
        return result_to_retrieval_result(query, self._service.search(query))

    def search(self, request: RetrievalRequest) -> RetrievalResult:
        """Alias for ``retrieve`` kept for interface symmetry."""
        return self.retrieve(request)

    def search_query(self, query: Query):
        """Run the native A4 pipeline and return the immutable SearchResult."""
        from retrieval.models import Query as _Query

        if not isinstance(query, _Query):
            raise ValueError("query must be a Query")
        return self._service.search(query)

    def with_plan(self, request: RetrievalRequest, **changes: object) -> RetrievalRequest:
        """Return a copy of ``request`` with updated plan fields (immutable)."""
        if not isinstance(request, RetrievalRequest):
            raise ValueError("request must be a RetrievalRequest")
        if request.plan is None:
            raise ValueError("request has no plan to update")
        return replace(request, plan=replace(request.plan, **changes))
