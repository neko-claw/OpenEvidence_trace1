from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from threading import BoundedSemaphore
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from a5.domain.models import AgentRun, AgentRunView
from a5.facade import BackendDependencies, ReplayCase, answer_text, to_ui_view
from deployment.a2.health import check_a2_readiness
from evaluation.preflight import check_manifest, load_manifest


BackendMode = Literal["replay", "mock", "research", "live"]


class TraceSink(Protocol):
    def write(self, run: AgentRun) -> None: ...


class JsonlTraceSink:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write(self, run: AgentRun) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(run.model_dump_json() + "\n")


class BackendServiceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_version: str = "track1-backend-v0.1.0"
    max_question_chars: int = Field(default=4000, ge=1, le=20000)
    max_concurrency: int = Field(default=2, ge=1, le=64)
    request_timeout_seconds: float = Field(default=60.0, gt=0, le=600)


class BackendReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["READY", "BLOCKED_EXTERNAL"]
    live_ready: bool
    config_version: str
    components: dict[str, str]
    blockers: list[str] = Field(default_factory=list)


class LiveCompositionUnavailable(RuntimeError):
    def __init__(self, readiness: BackendReadiness) -> None:
        self.readiness = readiness
        super().__init__("live composition is not ready")


def check_readiness(config: BackendServiceConfig | None = None) -> BackendReadiness:
    cfg = config or BackendServiceConfig()
    a2 = check_a2_readiness()
    manifests = {
        "a3": "evaluation/a3_embedding/manifest.json",
        "a4": "evaluation/a4_ablation/manifest.json",
        "a5": "evaluation/a5_verification/manifest.json",
    }
    a1_config = json.loads(Path("config/a1_classifier.json").read_text(encoding="utf-8"))
    a1_status = str(a1_config.get("policy_status", "PENDING_REVIEW"))
    components = {"a1": a1_status, "a2": a2.status}
    blockers = [f"A2:{item}" for item in a2.missing_requirements]
    for name, path in manifests.items():
        result = check_manifest(load_manifest(path))
        components[name] = result.status
        blockers.extend(f"{name.upper()}:{item}" for item in result.blockers)
    if a1_status != "APPROVED":
        blockers.append("A1:MEDICAL_POLICY_REVIEW_PENDING")
    return BackendReadiness(
        status="BLOCKED_EXTERNAL" if blockers else "READY",
        live_ready=not blockers,
        config_version=cfg.config_version,
        components=components,
        blockers=blockers,
    )


class BackendService:
    """Stable A6 service facade; mode isolation is enforced at construction."""

    def __init__(
        self,
        *,
        mode: BackendMode,
        config: BackendServiceConfig,
        dependencies: BackendDependencies | None = None,
        trace_sink: TraceSink | None = None,
    ) -> None:
        if mode in {"research", "live"} and dependencies is None:
            raise ValueError(f"{mode} service requires explicit dependencies")
        if mode in {"replay", "mock"} and dependencies is not None:
            raise ValueError("replay/mock service cannot receive injected dependencies")
        self.mode = mode
        self.config = config
        self.dependencies = dependencies
        self.trace_sink = trace_sink
        self._slots = BoundedSemaphore(config.max_concurrency)

    def answer(
        self,
        question: str,
        *,
        replay_case: ReplayCase = "PASS",
    ) -> AgentRun:
        if not question.strip():
            raise ValueError("question must not be blank")
        if len(question) > self.config.max_question_chars:
            raise ValueError("question exceeds configured size limit")
        if not self._slots.acquire(blocking=False):
            raise RuntimeError("backend concurrency limit reached")
        try:
            run = answer_text(
                question,
                mode=self.mode,
                dependencies=self.dependencies,
                replay_case=replay_case,
            )
            if self.trace_sink is not None:
                self.trace_sink.write(run)
            return run
        finally:
            self._slots.release()

    def answer_view(self, question: str, *, replay_case: ReplayCase = "PASS") -> AgentRunView:
        return to_ui_view(self.answer(question, replay_case=replay_case))

    def health(self) -> dict[str, object]:
        readiness = check_readiness(self.config) if self.mode == "live" else None
        return {
            "status": "ok",
            "mode": self.mode,
            "config_version": self.config.config_version,
            "live_ready": readiness.live_ready if readiness else False,
        }


def build_service(
    mode: BackendMode,
    *,
    config: BackendServiceConfig | None = None,
    dependencies_factory: Callable[[], BackendDependencies] | None = None,
    trace_sink: TraceSink | None = None,
) -> BackendService:
    cfg = config or BackendServiceConfig()
    if mode in {"replay", "mock"}:
        if dependencies_factory is not None:
            raise ValueError("replay/mock service cannot receive live dependencies")
        return BackendService(mode=mode, config=cfg, trace_sink=trace_sink)
    if mode == "research":
        if dependencies_factory is None:
            from deployment.track1_backend.research_factory import build_research_dependencies

            dependencies_factory = build_research_dependencies
        return BackendService(
            mode="research",
            config=cfg,
            dependencies=dependencies_factory(),
            trace_sink=trace_sink,
        )
    readiness = check_readiness(cfg)
    if not readiness.live_ready:
        raise LiveCompositionUnavailable(readiness)
    if dependencies_factory is None:
        raise LiveCompositionUnavailable(
            readiness.model_copy(update={"status": "BLOCKED_EXTERNAL", "live_ready": False, "blockers": [*readiness.blockers, "LIVE_DEPENDENCIES_NOT_CONFIGURED"]})
        )
    return BackendService(
        mode="live",
        config=cfg,
        dependencies=dependencies_factory(),
        trace_sink=trace_sink,
    )
