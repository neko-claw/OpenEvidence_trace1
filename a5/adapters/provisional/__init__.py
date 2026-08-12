"""Replaceable adapters for non-frozen A1-A4 branch contracts.

Nothing in this package is a canonical upstream schema. Each implementation is
versioned in ``config/integrations.yaml`` and is removed or narrowed when the
owning team freezes its contract.
"""

from a5.adapters.provisional.a1 import (
    A1QuestionAdapter,
    A1QuestionPayload,
    A1SafetyPolicyAdapter,
    A1SafetyVerdict,
)
from a5.adapters.provisional.a2 import (
    A2EvidenceAdapter,
    A2EvidencePayload,
    A2MCPRetriever,
    A2ToA3EvidenceAdapter,
)
from a5.adapters.provisional.a3 import (
    A3ChunkPayload,
    A3EvidenceAdapter,
    A3EvidencePayload,
    A3SpanPayload,
)
from a5.adapters.provisional.a4 import A4RAGRetriever
from a5.adapters.provisional.common import UpstreamContractError, UpstreamRetrievalError

__all__ = [
    "A1QuestionAdapter",
    "A1QuestionPayload",
    "A1SafetyPolicyAdapter",
    "A1SafetyVerdict",
    "A2EvidenceAdapter",
    "A2EvidencePayload",
    "A2MCPRetriever",
    "A2ToA3EvidenceAdapter",
    "A3ChunkPayload",
    "A3EvidenceAdapter",
    "A3EvidencePayload",
    "A3SpanPayload",
    "A4RAGRetriever",
    "UpstreamContractError",
    "UpstreamRetrievalError",
]
