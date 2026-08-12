from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence


class HashingEmbeddingProvider:
    """Fast deterministic multilingual hashing vectors for the research profile.

    This is a reproducible lexical-semantic fallback, not a trained medical
    embedding model. It keeps A3's EmbeddingProvider boundary intact while the
    formal embedding benchmark remains pending.
    """

    model_id = "multilingual-hashing-vectorizer"
    revision = "v0.1.0"
    source_kind = "deterministic_local"

    def __init__(self, dimensions: int = 512) -> None:
        if dimensions < 64:
            raise ValueError("dimensions must be at least 64")
        self.dimensions = dimensions

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode(text) for text in texts]

    def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode(text) for text in texts]

    def _encode(self, text: str) -> list[float]:
        normalized = text.casefold()
        latin = re.findall(r"[a-z0-9]+", normalized)
        chinese = re.findall(r"[\u4e00-\u9fff]", normalized)
        features = latin + [f"{a}_{b}" for a, b in zip(latin, latin[1:])]
        features += chinese + [a + b for a, b in zip(chinese, chinese[1:])]
        vector = [0.0] * self.dimensions
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimensions
            sign = 1.0 if value & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(item * item for item in vector))
        return [item / norm for item in vector] if norm else vector
