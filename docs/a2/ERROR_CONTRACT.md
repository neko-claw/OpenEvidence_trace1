# A2 Error Contract

`A2Error` contains `code`, `source`, safe `message`, `retryable`, optional
`http_status`, and optional sanitized `details`. Codes are `TIMEOUT`,
`RATE_LIMITED`, `UPSTREAM_HTTP_ERROR`, `UPSTREAM_PARSE_ERROR`,
`INVALID_REQUEST`, `NOT_FOUND`, `UNSUPPORTED_SOURCE`, `CACHE_ERROR`,
`MCP_ERROR`, and `INTERNAL_ERROR`.

Timeouts, connection errors, HTTP 429, and HTTP 5xx have bounded exponential
backoff with jitter. HTTP 400/401/403/404 and parse/schema errors are not
retried. API keys, authorization headers, environment dumps, and secret query
values are never included in errors, diagnostics, cache keys, or persistence.
Known tool failures return `ok=false` with no fabricated evidence. Citation
verification is fail-closed: unavailable verification is `UNKNOWN`, never
`VALID`.
