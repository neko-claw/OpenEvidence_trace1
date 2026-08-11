# A2 MCP Tools

The local read-only server is `a2.mcp.server` and uses official `mcp==2.0.0`
with stdio. Its six tools are:

| Tool | Input | Purpose |
|---|---|---|
| `search_pubmed` | `queries: list[str]`, `limit: int` | NCBI ESearch + EFetch |
| `search_europe_pmc` | same | Europe PMC core JSON search |
| `search_trials` | same | ClinicalTrials.gov API v2 search |
| `search_guidelines` | same | Approved local manifest/PDF search |
| `get_evidence` | `evidence_id`, `allow_live_lookup=false` | Exact store/native lookup |
| `validate_citation` | `evidence_id`, `allow_live_lookup=false` | VALID/INVALID/UNKNOWN verification |

Every tool returns `schema_version`, `ok`, formal `evidence`, diagnostics,
optional `error`, and optional non-evidence `result`. Search bounds come from
`config/a2.json`. One `A2MCPRetriever.retrieve()` call invokes exactly one MCP
tool; a connector may make multiple HTTP calls and reports that separately.

Run stdio with `pixi run a2-mcp`. Stdout is reserved for MCP framing. The
client supports official SDK in-process transport for tests and fresh stdio
subprocess transport for local use.
