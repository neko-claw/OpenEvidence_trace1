# A5 current development status

## A. Independently completed

- Pydantic domain and run-output models;
- explicit finite-state workflow and fail-closed gate;
- evidence research and citation audit skills;
- terminal/JSON tracing, deterministic finalization, and tests;
- A6/B4 entry and serialization contract.

## B. Completed through replaceable mocks/adapters

- Evidence retrieval through `EvidenceRetriever` / `MockEvidenceRetriever`;
- claim generation through `ClaimGenerator` / `MockClaimGenerator`;
- verification through `ClaimVerifier` / `RuleBasedClaimVerifier`;
- safety through `SafetyPolicy` / `DefaultSafetyPolicy`;
- configurable question classification and source planning.

## C. Waiting for formal upstream delivery

- A1 question/safety/refusal/termination policy;
- A2 Evidence/MCP schema and real MCP code;
- A3 PICO/span/evidence-level/provenance schema;
- A4 search/rerank result and diagnostics contracts;
- medical semantic verification and formal medical evaluation.

These C items do not block the offline A5 workflow and will be integrated via
the documented ports and adapters.
