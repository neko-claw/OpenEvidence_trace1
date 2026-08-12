from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from a2.config import A2Config, load_a2_config


class A2DeploymentStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    ready: bool
    config_version: str
    mcp_protocol_version: str
    enabled_sources: list[str] = Field(default_factory=list)
    guideline_manifest_version: str | None = None
    approved_guideline_count: int = 0
    missing_requirements: list[str] = Field(default_factory=list)


def check_a2_readiness(
    config: A2Config | None = None,
    *,
    environ: dict[str, str] | None = None,
) -> A2DeploymentStatus:
    """Validate configuration without making a network call or exposing secrets."""

    cfg = config or load_a2_config()
    env = environ if environ is not None else os.environ
    enabled = sorted(name for name, settings in cfg.sources.items() if settings.get("enabled") is True)
    missing: list[str] = []
    if "pubmed" in enabled:
        for name in ("NCBI_EMAIL", "NCBI_TOOL"):
            if not str(env.get(name, "")).strip():
                missing.append(name)
    manifest_version: str | None = None
    approved_count = 0
    if "guidelines" in enabled:
        path = Path(str(cfg.sources["guidelines"]["manifest_path"]))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            manifest_version = str(payload.get("manifest_version"))
            guidelines = payload.get("guidelines")
            if manifest_version != "1" or not isinstance(guidelines, list):
                missing.append("APPROVED_GUIDELINE_MANIFEST")
            else:
                approved_count = len(guidelines)
                if not guidelines:
                    missing.append("APPROVED_GUIDELINE_SOURCES")
        except (OSError, ValueError, TypeError):
            missing.append("APPROVED_GUIDELINE_MANIFEST")
    return A2DeploymentStatus(
        status="READY" if not missing else "BLOCKED_EXTERNAL",
        ready=not missing,
        config_version=cfg.schema_version,
        mcp_protocol_version=cfg.mcp_protocol_version,
        enabled_sources=enabled,
        guideline_manifest_version=manifest_version,
        approved_guideline_count=approved_count,
        missing_requirements=missing,
    )
