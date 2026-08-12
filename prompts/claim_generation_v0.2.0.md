---
name: claim_generation
version: 0.2.0
output_contract: Claim[]
---

Generate candidate factual statements from the retrieved evidence only. Each
statement must be decomposable into one verifiable fact. Citation values may be
selected only from the retrieved Evidence ID and span ID whitelists. Never
generate PMID, DOI, NCT, URL, or another external identifier. Use UNKNOWN for
uncertainty or matching fields that cannot be determined. It is correct to
return no claims when support is insufficient.
