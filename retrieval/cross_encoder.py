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

    ``s_final = alpha * calibrated_score + (1 - alpha) * feature_score``.
    Raw logits are retained for diagnostics but are never blended directly
    with the query-local [0, 1] feature score.  The caller must either declare
    that its model already emits probabilities or inject a calibration
    transform frozen on the development split.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        model_factory: Callable[[str], Any] | None = None,
        alpha: float = 0.5,
        *,
        score_semantics: str = "raw_logit",
        score_transform: Callable[[float], float] | None = None,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name must be a nonblank string")
        if model_factory is not None and not callable(model_factory):
            raise ValueError("model_factory must be callable or None")
        if not _finite(alpha) or not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be a finite number in [0, 1]")
        if score_semantics not in {"raw_logit", "probability", "calibrated_probability"}:
            raise ValueError("score_semantics must be raw_logit/probability/calibrated_probability")
        if score_transform is not None and not callable(score_transform):
            raise ValueError("score_transform must be callable or None")
        if score_semantics == "raw_logit" and score_transform is None:
            # This is a valid PENDING capability object.  Construction stays
            # cheap; scoring fails closed until calibration is explicitly set.
            pass
        self._model_name = model_name
        self._model_factory = model_factory
        self._alpha = alpha
        self._score_semantics = score_semantics
        self._score_transform = score_transform
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

    @property
    def score_semantics(self) -> str:
        return self._score_semantics

    @property
    def score_transform(self) -> Callable[[float], float] | None:
        return self._score_transform

    @property
    def is_ready(self) -> bool:
        return self._score_semantics != "raw_logit" or self._score_transform is not None

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
        if not self.is_ready:
            raise CrossEncoderError(
                "cross_encoder capability PENDING: raw logits require an explicit calibration transform"
            )
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

        calibrated = [self._calibrate(score) for score in scores]
        rescored: list[Candidate] = []
        for candidate, raw_score, ce_score in zip(normalized, scores, calibrated, strict=True):
            feature_score = candidate.rerank_score
            if feature_score is None:
                raise CrossEncoderError("candidate rerank_score must be present before blending")
            s_final = self._alpha * ce_score + (1.0 - self._alpha) * feature_score
            features = dict(candidate.feature_scores)
            features["cross_encoder_raw_score"] = raw_score
            features["cross_encoder_calibrated_score"] = ce_score
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

    def _calibrate(self, raw_score: float) -> float:
        if self._score_transform is not None:
            try:
                value = float(self._score_transform(raw_score))
            except Exception as error:
                raise CrossEncoderError(
                    f"cross_encoder calibration failed: {type(error).__name__}"
                ) from error
        else:
            value = raw_score
        if not _finite(value) or not 0.0 <= value <= 1.0:
            raise CrossEncoderError("cross_encoder calibrated score must be finite in [0, 1]")
        return value

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
