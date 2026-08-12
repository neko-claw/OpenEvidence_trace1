# A1–A5 final readiness matrix

Date: 2026-08-12

Conclusion: **engineering hardening is complete for all work not requiring
external data/approval, but A1–A5 live integration is BLOCKED_EXTERNAL**.

| Requirement | Evidence | Result |
|---|---|---|
| A1 free-text classifier Port/Adapter | `a1/classifiers/structured.py`; strict structured schema; no keyword fallback | DONE_ENGINEERING |
| A1 exception/timeout/low confidence | UNKNOWN→REFUSE and zero retrieval calls tests | DONE_ENGINEERING |
| A1 medical policy approval | Versioned checklist has no approval record | BLOCKED_EXTERNAL |
| A2 real public connectors | PubMed, Europe PMC, ClinicalTrials live tests 3/3 | PARTIAL |
| A2 Guidelines governance | Approved manifest contains zero entries | BLOCKED_EXTERNAL |
| A2 MCP deployment | stdio and streamable HTTP `/mcp`; offline health/readiness | DONE_ENGINEERING |
| A3 embedding selection | lexical + BGE-M3 candidate recorded; second baseline and formal data absent | BLOCKED_EXTERNAL |
| A3 reproducible formal evaluation | preflight refuses formal claims | BLOCKED_EXTERNAL |
| A4 same-pool R0–R3 | immutable pool/hash and stage tests | DONE_ENGINEERING |
| A4 ranking/quality isolation | strong types and tests; raw logits require explicit calibration | DONE_ENGINEERING |
| A4 Gate2 calibrated quality | calibration manifest has no gold/method/ECE/Brier | BLOCKED_EXTERNAL |
| A5 production generator contract | strict schema, Evidence/Span whitelist, external-ID and transport failure tests | DONE_ENGINEERING |
| A5 independent verifier contract | independent structured call; UNKNOWN/error insufficient; hard checks cannot be overridden | DONE_ENGINEERING |
| A5 medical verification | independent reviewed gold absent | BLOCKED_EXTERNAL |
| Live composition | construction aggregates preflights and refuses without readiness; no mock fallback | DONE_ENGINEERING / BLOCKED_EXTERNAL_RUN |
| A6/B4 schemas | v0.4.0 schemas and four replay fixtures validate | DONE |

No assertion of medical validation, clinical usability, production vector
capability, calibrated Gate2 quality or full live readiness is made.
