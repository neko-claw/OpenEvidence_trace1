from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from a3.domain.models import Evidence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config/a3.yaml"


def load_jsonl(path: str | Path) -> list[Evidence]:
    return [Evidence.model_validate(json.loads(line)) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]


class DeterministicSmokeEmbedding:
    """Offline fixture embedder; never presented as the production BGE index."""
    model_id = "a3-deterministic-smoke-v0.1"
    revision = "offline-fixture"

    @staticmethod
    def _encode(text: str) -> list[float]:
        vector = [0.0] * 32
        for token in text.casefold().replace(":", " ").split():
            vector[int(hashlib.sha256(token.encode()).hexdigest(), 16) % len(vector)] += 1.0
        norm = math.sqrt(sum(x*x for x in vector)) or 1.0
        return [x/norm for x in vector]

    def encode_documents(self, texts): return [self._encode(t) for t in texts]
    def encode_queries(self, texts): return [self._encode(t) for t in texts]
