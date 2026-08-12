# Independent live verification adapter

Use a transport instance and model configuration independent from generation.
Semantic output supplies only textual support; `RuleBasedClaimVerifier` remains
the authority for Evidence/span whitelist, PICO, time, numeric/unit and conflict
checks. UNKNOWN, malformed output and transport errors become INSUFFICIENT.
