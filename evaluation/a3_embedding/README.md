# A3 embedding evaluation

`manifest.json` intentionally contains no formal DEV/qrel paths. The checked-in
`data/dev` set is synthetic smoke data and cannot select a production model.
Fill the manifest only with licensed, reviewed data; add at least one reasonable
embedding baseline beyond lexical-only and BGE-M3; then approve thresholds.

Run preflight:

```powershell
pixi run eval-preflight evaluation/a3_embedding/manifest.json artifacts/live_acceptance/a3_preflight.json
```

Until it returns `READY`, production vector capability remains disabled and
lexical-only/UNKNOWN is the honest fallback.
