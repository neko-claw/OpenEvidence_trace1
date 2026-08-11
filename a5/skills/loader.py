from __future__ import annotations

import json
import importlib
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from a5.domain.models import StrictModel


SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class SkillManifest(StrictModel):
    name: str
    version: str
    description: str
    prompt_version: str
    prompt: str
    input_schema: str
    output_schema: str
    fixture_path: str
    implementation: str
    tags: list[str] = Field(default_factory=list)


class LoadedSkill(StrictModel):
    manifest: SkillManifest
    manifest_path: Path
    prompt_text: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    fixture: dict[str, Any]


class SkillLoader:
    """Load reusable Skill assets by configured name and version."""

    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = repository_root or Path(__file__).parents[2]

    def load(self, manifest_path: str | Path, *, expected_version: str | None = None) -> LoadedSkill:
        path = Path(manifest_path)
        if not path.is_absolute():
            path = self.repository_root / path
        manifest = SkillManifest.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
        if not SEMVER.fullmatch(manifest.version):
            raise ValueError(f"invalid Skill semantic version: {manifest.version}")
        if not SEMVER.fullmatch(manifest.prompt_version):
            raise ValueError(f"invalid Prompt semantic version: {manifest.prompt_version}")
        if expected_version is not None and manifest.version != expected_version:
            raise ValueError(
                f"Skill version mismatch: expected {expected_version}, got {manifest.version}"
            )

        def asset(asset_path: str) -> Path:
            resolved = (path.parent / asset_path).resolve()
            if not resolved.is_relative_to(self.repository_root.resolve()):
                raise ValueError("Skill asset escapes repository root")
            if not resolved.is_file():
                raise FileNotFoundError(resolved)
            return resolved

        prompt_path = asset(manifest.prompt)
        input_schema_path = asset(manifest.input_schema)
        output_schema_path = asset(manifest.output_schema)
        fixture_path = asset(manifest.fixture_path)
        module_name, separator, attribute = manifest.implementation.partition(":")
        if not separator or not module_name or not attribute:
            raise ValueError("Skill implementation must use module:attribute notation")
        implementation_module = importlib.import_module(module_name)
        if not hasattr(implementation_module, attribute):
            raise ValueError(f"Skill implementation target missing: {manifest.implementation}")
        return LoadedSkill(
            manifest=manifest,
            manifest_path=path,
            prompt_text=prompt_path.read_text(encoding="utf-8"),
            input_schema=json.loads(input_schema_path.read_text(encoding="utf-8")),
            output_schema=json.loads(output_schema_path.read_text(encoding="utf-8")),
            fixture=json.loads(fixture_path.read_text(encoding="utf-8")),
        )

    def load_by_name(self, name: str, version: str) -> LoadedSkill:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError(f"invalid Skill name: {name}")
        return self.load(
            self.repository_root / "a5" / "skills" / name / "manifest.yaml",
            expected_version=version,
        )


class PromptLoader:
    def __init__(self, prompt_dir: Path | None = None) -> None:
        self.prompt_dir = prompt_dir or Path(__file__).parents[2] / "prompts"

    def load(self, name: str, version: str) -> str:
        if not SEMVER.fullmatch(version):
            raise ValueError(f"invalid Prompt version: {version}")
        path = self.prompt_dir / f"{name}_v{version}.md"
        if not path.is_file():
            raise FileNotFoundError(path)
        text = path.read_text(encoding="utf-8")
        marker = f"version: {version}"
        if marker not in text:
            raise ValueError(f"Prompt version marker missing: {marker}")
        return text
