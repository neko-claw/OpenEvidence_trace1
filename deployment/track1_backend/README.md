# Track 1 backend composition

This is the A6-facing service boundary; it does not implement an A6 page.
`BackendService.answer()` returns the full `AgentRun` for B4 and
`answer_view()` returns the frozen `AgentRunView` for A6.

Modes are physically isolated:

- `replay`: versioned A5 contract fixtures only;
- `mock`: explicit offline workflow and visibly mock Evidence;
- `live`: refuses construction unless A1 review, A2 readiness, A3 selection,
  A4 calibration, A5 verification preflight and injected dependencies are all ready.

The service enforces request size and concurrency limits and exposes a JSONL
Trace sink. `request_timeout_seconds` is frozen in configuration for the future
HTTP host; synchronous in-process calls cannot preempt a running Python call,
so the host must enforce cancellation/deadlines when it is added.
