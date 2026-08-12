from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timezone
from enum import Enum
from math import isfinite
from typing import Any

from pydantic import BaseModel


class UpstreamContractError(ValueError):
    """The upstream payload cannot safely satisfy A5's compatibility view."""


class UpstreamRetrievalError(RuntimeError):
    """A retrieval provider failed or returned an invalid terminal status."""


def to_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise UpstreamContractError(f"expected mapping/model/dataclass, got {type(value).__name__}")


def read_field(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def enum_text(value: object) -> str:
    raw = value.value if isinstance(value, Enum) else value
    return str(raw).strip().casefold()


def parse_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("Z", "+00:00")
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(normalized)
        except ValueError:
            return None
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def positive_page(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        page = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return page if page >= 1 else None


def normalized_score(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return score if isfinite(score) and 0.0 <= score <= 1.0 else None


def join_terms(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    try:
        terms = [str(item).strip() for item in value if str(item).strip()]
    except TypeError:
        return None
    return "; ".join(terms) or None


def fixture_like(*values: object) -> bool:
    text = " ".join(str(value) for value in values if value is not None).casefold()
    return "[fixture]" in text or "fixture" in text or "mock-" in text or "mock:" in text
