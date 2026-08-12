from __future__ import annotations

import hashlib
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SECRET_NAMES = {"api_key", "apikey", "authorization", "token", "access_token"}


def normalized_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode(sorted(
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in SECRET_NAMES
    ))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def make_cache_key(method: str, url: str, params: dict[str, object] | None = None, body: object = None) -> str:
    """Create a deterministic cache key with secret parameters removed."""
    safe_params = {
        str(key): value for key, value in (params or {}).items()
        if str(key).lower() not in SECRET_NAMES
    }
    material = {
        "method": method.upper(), "url": normalized_url(url),
        "params": sorted(safe_params.items()), "body": body,
    }
    encoded = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
