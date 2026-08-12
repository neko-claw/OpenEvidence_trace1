"""Track-1 backend composition without collapsing A1--A5 ownership."""

from backend.config import BackendConfig, load_backend_config
from backend.source import A2EvidenceBatch, A2EvidenceSource
from backend.retriever import CoordinatedEvidenceRetriever

__all__ = [
    "A2EvidenceBatch",
    "A2EvidenceSource",
    "BackendConfig",
    "CoordinatedEvidenceRetriever",
    "load_backend_config",
]
