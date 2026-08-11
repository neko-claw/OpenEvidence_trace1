"""Integration package for the A4 branch.

``a5.retrieval_bridge`` adapts the A4 ``RetrievalService`` to the main
repository's ``a5.ports.EvidenceRetriever`` contract.  When merged into the
main ``openevidence-mvp`` project, ``a5.ports`` remains the canonical port
definition; this package only adds the adapter and re-exports the port types
so A4-only checkouts stay self-contained.
"""

from retrieval.ports import (
    EvidenceRetriever,
    Question,
    RetrievalRequest,
    RetrievalResult,
    SearchPlan,
    question_to_query,
    result_to_retrieval_result,
)

__all__ = [
    "EvidenceRetriever",
    "Question",
    "RetrievalRequest",
    "RetrievalResult",
    "SearchPlan",
    "question_to_query",
    "result_to_retrieval_result",
]
