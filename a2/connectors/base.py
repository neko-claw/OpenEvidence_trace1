from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable

import httpx

from a2.config import HTTPConfig
from a2.models.errors import A2Error, A2ErrorCode, A2Exception
from a2.storage.cache import make_cache_key
from a2.storage.sqlite_store import SQLiteStore


class RateLimiter:
    """Thread-safe minimum-interval limiter."""

    def __init__(self, requests_per_second: float, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._last = 0.0
        self._lock = Lock()
        self._sleep = sleeper

    def wait(self) -> None:
        with self._lock:
            delay = self.interval - (time.monotonic() - self._last)
            if delay > 0:
                self._sleep(delay)
            self._last = time.monotonic()


class A2HTTPClient:
    """Shared cached HTTP client with bounded retries and safe diagnostics."""

    def __init__(
        self, source: str, config: HTTPConfig, store: SQLiteStore | None = None,
        requests_per_second: float = 0, transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.source = source
        self.config = config
        self.store = store
        self._sleep = sleeper
        self._rate = RateLimiter(requests_per_second, sleeper)
        timeout = httpx.Timeout(
            connect=config.connect_timeout_seconds, read=config.read_timeout_seconds,
            write=config.total_timeout_seconds, pool=config.connect_timeout_seconds,
        )
        self.client = httpx.Client(timeout=timeout, headers={"User-Agent": config.user_agent}, transport=transport)
        self.request_count = 0
        self.retry_count = 0
        self.cache_hits = 0

    def request(self, method: str, url: str, *, params: dict[str, Any] | None = None, content: bytes | None = None) -> httpx.Response:
        key = make_cache_key(method, url, params, content.decode("utf-8", "replace") if content else None)
        if self.store:
            cached = self.store.cache_get(key)
            if cached:
                self.cache_hits += 1
                return httpx.Response(
                    cached["status_code"], content=cached["body"],
                    headers={"content-type": cached["content_type"] or "application/octet-stream"},
                    request=httpx.Request(method, url, params=params),
                )
        attempts = self.config.retry_count + 1
        for attempt in range(attempts):
            self._rate.wait()
            self.request_count += 1
            try:
                response = self.client.request(method, url, params=params, content=content)
                retryable_status = response.status_code == 429 or response.status_code >= 500
                if retryable_status and attempt + 1 < attempts:
                    self.retry_count += 1
                    self._backoff(attempt)
                    continue
                if response.status_code >= 400:
                    code = A2ErrorCode.RATE_LIMITED if response.status_code == 429 else A2ErrorCode.UPSTREAM_HTTP_ERROR
                    raise A2Exception(A2Error(
                        code=code, source=self.source,
                        message=f"{self.source} returned HTTP {response.status_code}",
                        retryable=retryable_status, http_status=response.status_code,
                    ))
                if self.store:
                    self.store.cache_put(
                        key, self.source, datetime.now(timezone.utc).isoformat(), response.status_code,
                        response.content, response.headers.get("content-type"),
                    )
                return response
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                if attempt + 1 < attempts:
                    self.retry_count += 1
                    self._backoff(attempt)
                    continue
                code = A2ErrorCode.TIMEOUT if isinstance(exc, httpx.TimeoutException) else A2ErrorCode.UPSTREAM_HTTP_ERROR
                raise A2Exception(A2Error(code=code, source=self.source, message=f"{self.source} request failed", retryable=True)) from exc
        raise AssertionError("bounded retry loop exhausted unexpectedly")

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.request("GET", url, params=params)
        try:
            payload = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source=self.source, message=f"invalid {self.source} JSON")) from exc
        if not isinstance(payload, dict):
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source=self.source, message=f"unexpected {self.source} JSON shape"))
        return payload

    def _backoff(self, attempt: int) -> None:
        delay = self.config.backoff_seconds * (2 ** attempt)
        self._sleep(delay + random.uniform(0, delay * 0.1) if delay else 0)

    def diagnostics(self) -> dict[str, Any]:
        return {"cache_hit": self.cache_hits > 0, "upstream_request_count": self.request_count, "retry_count": self.retry_count}
