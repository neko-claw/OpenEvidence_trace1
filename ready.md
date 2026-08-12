# A1–A5 readiness (2026-08-12)

Overall status: **PARTIAL / BLOCKED_EXTERNAL**. Do not claim
`A1–A5 ENGINEERING READY FOR A6 LIVE INTEGRATION` or `MEDICALLY VALIDATED`.
Replay/mock A6 integration is ready; live construction is deliberately blocked.

## Recovery

- Working directory: `D:\A_demo_recovered`
- Protected source snapshot: `D:\A_demo` (unchanged; broken worktree link retained)
- Recovery method: independent `git init` import because remote TLS/credentials were unavailable
- Snapshot verification: 358 included files, SHA-256 missing=0, extra=0, changed=0
- Expected old commit marker: `bb5218f17d9f73b878c2a6337423a602c5421d85` (history not claimed/restored)
- Branch: `feature/a1-a5-live-completion`
- Recovery baseline: `8d82924c92200b65ecdac4526e0636f1cd617450`

## Module matrix

| Module | Status | Proven work | Remaining external blocker |
|---|---|---|---|
| A1 | PARTIAL | Injected structured classifier, strict schema, low-confidence/error UNKNOWN, Gate0 zero-tool stop, effective version snapshot | Medical policy review and threshold validation |
| A2 | PARTIAL | PubMed/Europe PMC/ClinicalTrials live 3/3; six-tool MCP discovery; cache/error envelope; stdio/HTTP deployment and health | NCBI identity config and approved/licensed Guidelines manifest |
| A3 | BLOCKED_EXTERNAL | Runtime manifest/provenance/index boundaries and formal-eval preflight; lexical fallback remains honest | Licensed reviewed DEV/qrels, second embedding baseline, model access, approved thresholds |
| A4 | BLOCKED_EXTERNAL | Immutable same-pool R0–R3, raw-logit fail-closed, ranking/quality separation, formal calibration preflight | Separate calibration gold, calibrated scorer, ECE/Brier, approved thresholds |
| A5 | PARTIAL | Structured generator/verifier adapters, whitelist/schema/transport failure gates, deterministic hard checks, PASS/WARN/REFUSE/ERROR contracts | Independent medically reviewed verification gold and approved thresholds |
| Live composition | BLOCKED_EXTERNAL | Stable service facade, replay/mock/live isolation, health/readiness, limits, Trace sink, no mock fallback | All A1–A5 live preflights must be READY |
| A6/B4 contract | DONE | `AgentRun` / `AgentRunView` v0.4.0 and four replay fixtures validate without Schema drift | None for replay integration; live depends on above |

## Actual acceptance results

- `pixi run test`: **534 passed, 3 skipped**; skipped tests are opt-in live-network tests and are not counted as live pass.
- `pixi run demo`: **PASS / WARN / REFUSE** (mock-only).
- `pixi run backend-demo`: **PASS** (mock A1→A2 MCP→A3→A4→A5 coordination).
- `A2_LIVE_TESTS=1 ... tests/test_a2_live.py`: **3 passed** (PubMed, Europe PMC, ClinicalTrials).
- `tests/live/a2 + tests/live/backend`: **6 passed** (readiness/mode isolation; not a full live medical request).
- Existing DEV evaluation: smoke/proxy only — Recall@50=1.000, nDCG@8=0.750, span-proxy Recall@8=1.000, claim-chunk coverage@8=1.000.
- A3/A4/A5 formal preflights: **BLOCKED_EXTERNAL**; no formal metric claim emitted.
- `compileall`, A1/A2/A3/A5 Schema exporters and `git diff --check`: passed.
- Secret pattern, new-change branding, and mock-external-identifier scans: no new violation found.

## Exact next actions

1. Authenticate and compare history before any push:

   ```powershell
   gh auth login -h github.com
   git fetch origin --prune
   git cat-file -e bb5218f17d9f73b878c2a6337423a602c5421d85^{commit}
   ```

   Do not push this independently initialized history until the old history is compared and reconciled safely.

2. Configure A2 and approved Guidelines:

   ```powershell
   $env:NCBI_EMAIL='project-owner@example.org'
   $env:NCBI_TOOL='OpenEvidence'
   pixi run a2-health
   $env:A2_LIVE_TESTS='1'
   pixi run python -m pytest tests/test_a2_live.py -q --basetemp .a2-live-final-pytest -p no:cacheprovider
   ```

3. Supply reviewed manifests and run formal preflights:

   ```powershell
   pixi run eval-preflight evaluation/a3_embedding/manifest.json artifacts/live_acceptance/a3_preflight.json
   pixi run eval-preflight evaluation/a4_ablation/manifest.json artifacts/live_acceptance/a4_preflight.json
   pixi run eval-preflight evaluation/a5_verification/manifest.json artifacts/live_acceptance/a5_preflight.json
   ```

4. After owners approve A1 policy, record approval in
   `docs/a1/safety_policy_review_checklist.md` and set
   `config/a1_classifier.json:policy_status` to `APPROVED`; rerun the entire acceptance suite.
