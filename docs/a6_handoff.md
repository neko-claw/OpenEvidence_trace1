# A6 handoff (contract v0.4.0)

## Stable entry points

- Service: `deployment.track1_backend.build_service(mode)`
- Full run for B4: `BackendService.answer(question, replay_case=...) -> AgentRun`
- Safe A6 view: `BackendService.answer_view(...) -> AgentRunView`
- Existing direct facade: `a5.facade.answer_text(...)` and `a5.facade.to_ui_view(...)`

Do not import mock adapters or workflow internals from A6.

## Modes

- `replay`: consumes `contracts/a5/v0.4.0/fixtures/{pass,warn,refuse,error}.json`.
- `mock`: executes explicit synthetic fixtures; Evidence cards remain `mock=true`
  and URLs are hidden.
- `live`: refuses construction until all readiness checks pass and explicit
  production dependencies are injected. It never switches to mock.

## AgentRunView fields

`run_id`, `decision`, `answer_text`, `included_claim_ids`, `reason_codes`,
`warnings`, `limitations`, `evidence_cards`, `trace`, `error_code`,
`error_message`.

Canonical Schema: `contracts/a5/v0.4.0/schemas/AgentRunView.schema.json`.
Full B4 Schema: `contracts/a5/v0.4.0/schemas/AgentRun.schema.json`.

## Rendering rules

- Render only included SUPPORTED claims.
- For REFUSE/ERROR, do not surface rejected claim text as an answer.
- Show warnings and limitations explicitly.
- Mark mock cards as test data; never show a mock URL.
- Use structured Trace fields; do not parse the human-readable trace text.
- Display only sanitized `error_message`; never expose `AgentRun.error` directly.

## Health and errors

`BackendService.health()` returns mode, config version and `live_ready` without
secrets. Current live readiness is false. Expected public error categories are
`safety_denied`, `retrieval_insufficient`, `unsupported_claim`,
`illegal_citation`, `upstream_unavailable` and `internal_error` as frozen in the
view Schema/enums.

## Replay examples

```python
from deployment.track1_backend import build_service

service = build_service("replay")
view = service.answer_view("ignored in replay", replay_case="WARN")
```

The four replay files are mock-only contract examples, not medical evidence.
