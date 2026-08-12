# A3 data contract v0.2

This package is A3's versioned downstream contract and engineering fixture. It is
not A2's final Evidence schema and does not claim that the mock records are medical
evidence.

- `schemas/`: Pydantic-generated JSON Schema for `Evidence`, `Chunk`,
  `EvidenceSpan`, `SearchHit`, and `IndexManifest`.
- `fixtures/mock_evidence.jsonl`: deterministic offline records. Every record has
  `mock=true`, a `MOCK-` ID, and no PMID, DOI, NCT ID, guideline identity, or URL.

Regenerate schemas with `python -m a3.contracts.export`.
