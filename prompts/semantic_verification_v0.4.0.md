---
name: semantic_verification
version: 0.4.0
output_contract: SemanticVerificationOutput
---

Evaluate one atomic claim against only the supplied cited Evidence spans.
Return exactly one structured status: SUPPORTED, CONTRADICTED, INSUFFICIENT, or
UNKNOWN. SUPPORTED requires direct semantic support from the cited spans; topic
similarity or retrieval rank is not support. If population, intervention,
comparator, outcome, time, numeric value, unit, or direction conflicts, do not
return SUPPORTED. UNKNOWN and missing information are not support. Never add a
new Evidence ID, span ID, PMID, DOI, NCT identifier, guideline identifier, URL,
or medical fact.
