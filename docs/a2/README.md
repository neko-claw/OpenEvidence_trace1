# OpenEvidence A2

A2 implements `Source → Fetch → Normalize → Cache → Dedup → A2Evidence → MCP`
and a compatibility adapter into A5. It does not implement embeddings, BM25,
vector search, reranking, PICO extraction, evidence-level prediction, medical
reasoning, safety gates, claim verification, or UI. A3/A4/A1/A5/A6 retain those
responsibilities.

```text
PubMed / Europe PMC / ClinicalTrials.gov / approved local guidelines
  → httpx + bounded retry + SQLite HTTP cache
  → A2Evidence (`a2-evidence-v1`) + conservative dedup
  → SQLite / deterministic JSONL
  → local MCP v2 server → MCP client
  → A2MCPRetriever → EvidenceRetriever → unchanged A5 workflow
```

## Environment and configuration

Use the existing Python 3.11 Pixi environment. `config/a2.json` freezes schema,
MCP 2.0.0/protocol, timeouts, retry/backoff, limits, storage paths, official
base URLs, and source flags. Secrets are environment-only:

```text
NCBI_API_KEY=
NCBI_EMAIL=
NCBI_TOOL=OpenEvidence
```

No NCBI key is required for offline tests. Runtime DB/cache lives under
`data/a2/` and is ignored by Git. HTTP cache keys remove secret parameters.

## Run

```powershell
pixi run test
pixi run a2-smoke       # offline MCP protocol fixture
pixi run a2-mcp         # local stdio server; stdout is protocol-only
```

`A2MCPClient(build_mcp_server(fixture_service))` provides official SDK direct
transport for tests. `A2MCPClient.local_stdio()` launches the local server.
Production A5 use is explicit through `a2.composition.build_local_a2_retriever`;
the default and demo A5 workflows keep their existing mock retriever and never
access the network.

Set `A2_LIVE_TESTS=1` only for explicit live smoke. Default pytest and smoke are
offline. Recorded public subsets use real public identifiers; synthetic parser
fixtures are labeled and are never presented as medical evidence.

## Storage and export

`SQLiteStore` creates `evidence`, `http_cache`, `source_alias`, and
`schema_meta` with WAL mode and indexed identifier/hash columns.
`a2.storage.jsonl_export.export_jsonl` emits UTF-8, deterministic-ID-order,
round-trippable A2 JSONL. Guideline ingestion reads only the versioned
`config/a2_guidelines.json` whitelist and extracts natural PDF pages with
PyMuPDF; no open-web crawler or complex A3 chunking is included.

## Known limitations

- Search does not automatically fetch Europe PMC full text; `get_full_text` is
  explicit to control latency/cache/copyright exposure.
- HTTPX enforces connect/read/write/pool dimensions; the configured total is
  also used as the write bound, not a separate wall-clock cancellation scope.
- Citation lookup is local by default. A well-formed absent ID is `UNKNOWN`
  unless exact live lookup is explicitly allowed.
- A2 supplies no A4 score and no A3 span, so A5 gates correctly treat those as
  unknown until the respective adapters are integrated.
