"""Optional Cross-Encoder reranking (P1) with explainable score blending."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from math import isfinite
from numbers import Real
from typing import Any

from .models import Candidate, Query


class CrossEncoderError(Exception):
    """Stable error raised when Cross-Encoder loading or scoring fails."""


class CrossEncoderScorer:
    """Lazy, injectable Cross-Encoder adapter producing ``s_final`` blends.

    ``s_final = alpha * cross_encoder_score + (1 - alpha) * feature_score``.
    The raw Cross-Encoder score and the blend are both retained in
    ``feature_scores`` next to the explainable features; the Cross-Encoder
    alone never decides a medical conclusion.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        model_factory: Callable[[str], Any] | None = None,
        alpha: float = 0.5,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name must be a nonblank string")
        if model_factory is not None and not callable(model_factory):
            raise ValueError("model_factory must be callable or None")
        if not _finite(alpha) or not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be a finite number in [0, 1]")
        self._model_name = model_name
        self._model_factory = model_factory
        self._alpha = alpha
        self._model: Any = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_factory(self) -> Callable[[str], Any] | None:
        return self._model_factory

    @property
    def alpha(self) -> float:
        return self._alpha

    def score(self, query: Query, candidates: Sequence[Candidate]) -> list[Candidate]:
        """Return candidates re-ranked by the blended score, retaining features."""
        if not isinstance(query, Query):
            raise ValueError("query must be a Query")
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise ValueError("candidates must be a sequence of Candidate")
        normalized = tuple(candidates)
        if any(not isinstance(candidate, Candidate) for candidate in normalized):
            raise ValueError("candidates must contain only Candidate values")
        if not normalized:
            return []
        model = self._ensure_model()
        pairs = [(query.text, candidate.chunk.text) for candidate in normalized]
        try:
            raw = model.predict(pairs)
            scores = [float(value) for value in raw]
        except CrossEncoderError:
            raise
        except Exception as error:
            raise CrossEncoderError(f"cross_encoder predict failed: {type(error).__name__}") from error
        if len(scores) != len(normalized):
            raise CrossEncoderError(
                f"cross_encoder count mismatch: expected {len(normalized)} scores, got {len(scores)}"
            )
        if any(not _finite(score) for score in scores):
            raise CrossEncoderError("cross_encoder returned non-finite scores")

        rescored: list[Candidate] = []
        for candidate, ce_score in zip(normalized, scores):
            feature_score = candidate.rerank_score
            if feature_score is None:
                raise CrossEncoderError("candidate rerank_score must be present before blending")
            s_final = self._alpha * ce_score + (1.0 - self._alpha) * feature_score
            features = dict(candidate.feature_scores)
            features["cross_encoder_score"] = ce_score
            features["s_final"] = s_final
            rescored.append(
                Candidate(
                    chunk=candidate.chunk,
                    bm25_rank=candidate.bm25_rank,
                    vector_rank=candidate.vector_rank,
                    bm25_raw_score=candidate.bm25_raw_score,
                    vector_raw_score=candidate.vector_raw_score,
                    rrf_score=candidate.rrf_score,
                    rerank_score=feature_score,
                    feature_scores=features,
                )
            )
        rescored.sort(key=lambda candidate: (-float(candidate.feature_scores["s_final"]), candidate.chunk.chunk_id))
        return rescored

    def _ensure_model(self) -> Any:
        if self._model is None:
            factory = self._model_factory if self._model_factory is not None else _default_model_factory
            try:
                self._model = factory(self._model_name)
            except Exception as error:
                raise CrossEncoderError(
                    f"cross_encoder model could not be loaded: {type(error).__name__}"
                ) from error
        return self._model


def _default_model_factory(model_name: str) -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name)


def _finite(value: object) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False
