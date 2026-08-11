# Repository working rules

- Preserve A5's finite-state workflow and public `answer(...)->AgentRun` API.
- A1 safety, A2 Evidence/MCP, A3 PICO/span, and A4 search/rerank remain behind
  Protocol/Adapter boundaries. Prefer a new adapter over workflow rewrites.
- Never present mock fixtures as medical evidence. Mock records must set
  `mock=true` and must not use fabricated PMID, DOI, NCT, URL, or guideline IDs.
- Gate0 and Gate6 are fail-closed. UNKNOWN safety or verification data must not
  silently become ALLOW/SUPPORTED.
- Versions and thresholds belong in `config/` or versioned Skill/Prompt assets,
  and the effective values must be preserved in `AgentRun`.
- Run `pixi run test` and `pixi run demo` before merge-readiness claims.
- Update local `/log.md` after each task, but never stage or commit that file.
