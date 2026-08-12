# Track-1 backend integration contract

The A5 finite-state workflow and `answer(...)->AgentRun` contract remain the
stable control boundary. A1–A4 are integrated through Ports/Adapters; a later
upstream revision should add or replace an adapter before changing the workflow.

## Current integrated path

```text
A5 Gate0 -> A1 SafetyPolicy
A5 ToolBudget -> A2 MCP search tool
A2 Evidence -> A2ToA3Normalizer -> A3 Evidence/Chunk/Span/SearchHit
A3 lexical/vector hits -> A4 InitialCandidatePool -> R0/R1/R2/R3
A4 SearchResult -> A5 EvidenceRetriever adapter -> Gate1/Gate2
A5 Gate3/Gate4 -> Claim[] -> citation_audit/Gate5 -> Gate6
AgentRun -> A6 AgentRunView / B4 full JSON
```

The offline acceptance path is built by `backend.demo.build_fixture_workflow`.
It uses the real in-process MCP server/client and real contracts, but every
record/model/quality score is explicitly a fixture and is not medical evidence.

## A1 — safety and termination

Delivered:

- `SafetyPolicyInput/Output` and deterministic reference policy;
- `a1.ports.SafetySignalClassifier` for free-text signal extraction;
- `a1.adapters.A1SafetyPolicyAdapter(policy=None, classifier=None)`;
- UNKNOWN on missing classifier/signals, exceptions or incomplete output;
- Gate0 executes before classification, retrieval and generation.

Production dependency:

- a validated classifier that maps a user question to the frozen A1 safety
  signals;
- final A1 question taxonomy, refusal policy and termination thresholds;
- reviewed datasets/qrels and provenance required by the planning document.

Replacement point: inject the classifier/policy into `A1SafetyPolicyAdapter`.
Do not add medical safety keywords inside the A5 workflow.

## A2 — Evidence and read-only MCP tools

Delivered:

- `a2-evidence-v1`, structured tool/error envelopes and checked-in schemas;
- MCP tools `search_pubmed`, `search_europe_pmc`, `search_trials`,
  `search_guidelines`, `get_evidence`, `validate_citation`;
- `A2MCPRetriever` for the direct A2→A5 boundary;
- `A2ToA3Normalizer.normalize`, `.normalize_many`, and
  `.normalize_tool_response` for the integrated A2→A3 path;
- explicit `mock` contract: mock records cannot carry URL, PMID, DOI, NCT or
  guideline identifiers;
- `backend.A2EvidenceSource`: one `acquire` performs at most one approved MCP
  search call and never retries invisibly.

Production dependency: live connector credentials/rate limits and source
operations. They are environment/deployment concerns, not A5 logic.

Replacement point: inject a deployed A2 MCP client into `A2EvidenceSource`.

## A3 — evidence, PICO, spans and index provenance

Delivered:

- versioned Evidence/PICO/Chunk/EvidenceSpan/SearchHit/IndexManifest models;
- document-relative chunk offsets plus chunk/document span offsets;
- content/evidence hashes, tombstone/live state and runtime-effective manifest;
- BM25 and vector indexes that return typed SearchHit provenance;
- `a5.adapters.a3.adapt_a3_selection` and the integrated
  `build_initial_pool_from_a3_hits` handoff;
- Embedding ownership through an injected A3 `EmbeddingProvider`.

Unknown fields remain null/UNKNOWN. The normalizer and adapters never invent
PICO, spans, evidence level or retrieval quality.

Production dependency: freeze and report the selected embedding model/revision,
DEV Recall@50, latency and reproducible index rebuild. BGE-M3 is only a
candidate provider; it is not loaded or silently selected by A4.

Replacement point: inject the approved A3 `EmbeddingProvider` and persistent
indexes. A4 must not create a second embedding stack.

## A4 — retrieval, rerank and calibrated quality

Delivered:

- immutable `InitialCandidatePool` and one-retrieval ablation boundary;
- `RetrievalService.retrieve_initial_pool`, `.search_from_pool`, and
  `.search_condition`;
- R0 BM25+Vector+RRF; R1 feature rerank+MMR; R2 explicit calibrated
  Cross-Encoder; R3 R2+support gate;
- auditable condition, pool hash, stage trace, feature/rank log and structured
  degradation;
- strict distinction between query-local ranking and optional calibrated
  cross-query quality.

R2/R3 fail closed when the required capability is absent. Raw Cross-Encoder
logits are never converted into an unearned probability. A4 token overlap and
support hints remain diagnostics and never become A5 Gate5 `SUPPORTED`.

Production dependency: if P1 is enabled, supply a pinned Cross-Encoder,
calibration transform and same-pool R0–R3 nDCG/support/latency evaluation. A
separate `CalibratedQualityScorer` must be validated before Gate2 uses its
scores.

Replacement point: inject those optional Ports into `RetrievalService` or
`CoordinatedEvidenceRetriever`; the A5 workflow stays unchanged.

## A5 — trustworthy control layer

Delivered:

- versioned Skill packages, Prompt assets, JSON Schema and fixtures;
- bounded Skill routing and actual tool-call budget enforcement;
- fail-closed Gate0/Gate1/Gate2/Gate3/Gate4/Gate5/Gate6;
- CRAG-style retrieval quality decision and corrective source retry;
- FActScore-style atomic Claim splitting;
- ALCE-style Evidence/Span citation validity, precision and coverage checks;
- structured generation and independent semantic-verifier Ports;
- PASS/WARN/REFUSE finalizer that publishes only supported claims;
- terminal/JSON Trace and runtime config/version snapshot.

The deterministic P0 verifier is not medical NLI. Exact span match can support
an atomic claim; paraphrase/unknown entailment remains INSUFFICIENT unless an
independent verifier is explicitly injected and its output passes all other
Gate5 checks.

## A6 — UI contract

Use the safe view contract:

```python
from a5.facade import answer_text, to_ui_view

run = answer_text("question", mode="replay", replay_case="PASS")
view = to_ui_view(run)
```

Schemas and PASS/WARN/REFUSE/ERROR replays are in `contracts/a5/v0.4.0/`.
`AgentRunView` contains decision, publishable answer, reason codes, warnings,
limitations, cited evidence cards, trace and sanitized errors. Candidate or
refused Claim text is not exposed as a publishable answer.

Live mode requires `BackendDependencies(workflow=...)`; missing dependencies
raise a configuration error and mock evidence in a live run forces REFUSE.

## B4 — batch/evaluation contract

B4 persists `AgentRun.model_dump(mode="json")` per question. Run ID, versions,
effective configuration, tool-call indices, budget, stage/gate events, evidence
and claim diagnostics remain available for aggregation. Batch scheduling is not
implemented inside A5.

## Integration procedure for future deliveries

1. Read the delivered schemas, code and sample envelopes.
2. Produce an Integration Diff against the current Port/model.
3. Classify each change as direct replacement, adapter required or schema
   conflict.
4. Add the smallest adapter and preserve A5 transitions/public contracts.
5. Run contract tests, full `pixi run test` and both demos.
6. Remove only temporary assumptions made obsolete by the frozen delivery.
7. Update this file, runtime versions and checked-in schemas/fixtures.

## Explicitly pending before a clinical or live-production claim

- validated A1 free-text safety classifier and final policy;
- live A2 connector deployment and source governance;
- approved A3 embedding/index evaluation;
- optional A4 Cross-Encoder/quality calibration and formal ablation;
- independent medical semantic verifier and formal medical-effect evaluation;
- A6 deployment and B4 batch runner.

These do not block A6 from integrating against replay/mock contracts, but they
do block any claim that the system is clinically validated or production-live.
