# A2 deployment

This composition root exposes the existing six read-only A2 MCP tools. It does
not implement evidence logic. `--health` performs an offline readiness check and
returns `BLOCKED_EXTERNAL` when required NCBI identity settings or an approved
guideline manifest are absent. Startup fails closed in that state.

```powershell
pixi run python -m deployment.a2.server --health
pixi run python -m deployment.a2.server --transport stdio
pixi run python -m deployment.a2.server --transport streamable-http --host 127.0.0.1 --port 8000
```

The HTTP MCP path is `/mcp`; request bodies are capped at 1 MiB. Configure
`NCBI_EMAIL`, `NCBI_TOOL`, optional `NCBI_API_KEY`, and approved entries in
`config/a2_guidelines.json`. Do not commit credentials or downloaded PDFs.
