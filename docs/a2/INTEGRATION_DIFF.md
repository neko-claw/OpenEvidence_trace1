# A2 → A5 Integration Diff

This diff freezes the `a2-evidence-v1` compatibility boundary before the A2
implementation. `A2Evidence` is authoritative for source ingestion; A5 keeps
its narrow `EvidenceRecord` compatibility model. A3 remains responsible for
final PICO, chunk, span, and provenance semantics.

| A2 field | A5 field | status | conversion | notes |
|---|---|---|---|---|
| `schema_version` | `source_metadata.a2_schema_version` | DIAGNOSTIC_ONLY | copy | Frozen as `a2-evidence-v1`. |
| `id` | `id` | DIRECT | copy stable source ID | Never invented; source-native identity only. |
| `source_type` | `source_type` | DIRECT | enum value to string | Unknown routes do not fall back. |
| `title` | `title` | DIRECT | copy | Required non-empty source text. |
| `abstract_or_chunk` | `content` | MAPPED | copy | A2 does not perform A3 chunking. |
| `authors` | `source_metadata.authors` | DIAGNOSTIC_ONLY | copy list | Empty list stays empty. |
| `published_at` | `published_at` | DIRECT | timezone-aware datetime | Missing stays `None`. |
| `url` | `source_metadata.url` | DIAGNOSTIC_ONLY | copy | Only an upstream or deterministic official native-ID URL. |
| `pmid` | `source_metadata.pmid` | DIAGNOSTIC_ONLY | copy | Missing stays `None`; never fabricated. |
| `doi` | `source_metadata.doi` | DIAGNOSTIC_ONLY | normalized copy | Missing stays `None`; never fabricated. |
| `nct_id` | `source_metadata.nct_id` | DIAGNOSTIC_ONLY | uppercase copy | Missing stays `None`; never fabricated. |
| `guideline_name` | `source_metadata.guideline_name` | DIAGNOSTIC_ONLY | copy | Comes only from approved manifest. |
| `page` | `source_metadata.page` | DIAGNOSTIC_ONLY | copy integer | No A5 span is created merely from a page. |
| `evidence_level` | `evidence_level` | DIRECT | copy only when explicitly supplied | A2 never predicts a level. |
| `population` | `population` | DIRECT | copy only when explicit | A2 never extracts PICO. |
| `intervention` | `intervention` | DIRECT | copy only when explicit | A2 never extracts PICO. |
| `comparator` | `comparator` | DIRECT | copy only when explicit | A2 never extracts PICO. |
| `outcome` | `outcome` | DIRECT | copy only when explicit | A2 never extracts PICO. |
| `fetched_at` | `source_metadata.fetched_at` | DIAGNOSTIC_ONLY | ISO 8601 copy | Excluded from content hash. |
| `content_hash` | `source_metadata.content_hash` | DIAGNOSTIC_ONLY | copy SHA-256 | Stable core-content hash. |
| `source_metadata` | `source_metadata.source_metadata` | MAPPED | nested copy | Preserves native metadata without flattening conflicts. |
| canonical key | `source_metadata.canonical_key` | MAPPED | compute during persistence/adaptation | DOI > PMID > NCT > guideline ID > native ID. |
| aliases | `source_metadata.aliases` | MAPPED | copy persisted aliases | Records all contributing sources. |
| merge conflicts | `source_metadata.dedup_conflicts` | DIAGNOSTIC_ONLY | copy safe field/value provenance | Conflicts are not medically resolved. |
| retrieval score | `retrieval_score` | MISSING | always `None` | Owned by A4; A2 does not rank. |
| spans | `spans` | MISSING | always `[]` | Owned by A3; A2 does not invent span IDs. |
| conflict evidence IDs | `conflicts_with_ids` | MISSING | always `[]` | A2 merge conflicts are metadata conflicts, not medical contradiction claims. |
| mock flag | `mock` | MAPPED | always `False` for A2 connector output | Test doubles stay outside formal evidence and cannot masquerade as evidence. |

## Compatibility decisions

- Mapped into the A5 public view: identity, content, source, title, explicit
  dates, explicit PICO, and explicit evidence level.
- Preserved as diagnostics: identifiers, URL, authors, fetch/hash information,
  canonical key, aliases, native metadata, and conservative merge conflicts.
- Missing by design: A4 score and A3 spans. They remain `None`/`[]`.
- Dropped fields: none. Source-specific fields remain nested metadata.
- Conflicts: A2 does not choose a medically “correct” value. Existing non-null
  values remain primary and alternatives are recorded in diagnostics.

No change to `a5/agent/workflow.py`, `AgentRun`, or the public
`answer(question, workflow=...) -> AgentRun` API is required.
