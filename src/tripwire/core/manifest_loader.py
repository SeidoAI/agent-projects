"""Load and validate `templates/artifacts/manifest.yaml`.

Validation runs in two steps:
  1. Pydantic parses the YAML shape (required fields, extras forbidden).
  2. `produced_at` / `produced_by` / `owned_by` strings are checked
     against the active `artifact_phase` and `agent_type` enums
     (project override → packaged default → StrEnum fallback).

Both callers — the validator and session readiness — route through here
so enum validation stays in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from tripwire.core.enum_loader import load_enum
from tripwire.models.manifest import ArtifactManifest


@dataclass(frozen=True)
class ManifestLoadFinding:
    """Structured error from manifest load — consumed by validator to emit CheckResults."""

    code: str
    field: str | None
    message: str


def _validate_against_enums(
    manifest: ArtifactManifest, project_dir: Path
) -> list[ManifestLoadFinding]:
    findings: list[ManifestLoadFinding] = []
    allowed_phases = set(load_enum(project_dir, "artifact_phase"))
    allowed_agents = set(load_enum(project_dir, "agent_type"))

    for entry in manifest.artifacts:
        if entry.produced_at not in allowed_phases:
            findings.append(
                ManifestLoadFinding(
                    code="manifest_schema/produced_at_valid",
                    field="produced_at",
                    message=(
                        f"Entry {entry.name!r} has produced_at="
                        f"{entry.produced_at!r} which is not in the active "
                        f"artifact_phase enum: {sorted(allowed_phases)}"
                    ),
                )
            )
        if entry.produced_by not in allowed_agents:
            findings.append(
                ManifestLoadFinding(
                    code="manifest_schema/produced_by_valid",
                    field="produced_by",
                    message=(
                        f"Entry {entry.name!r} has produced_by="
                        f"{entry.produced_by!r} which is not in the active "
                        f"agent_type enum: {sorted(allowed_agents)}"
                    ),
                )
            )
        if entry.owned_by is not None and entry.owned_by not in allowed_agents:
            findings.append(
                ManifestLoadFinding(
                    code="manifest_schema/owned_by_valid",
                    field="owned_by",
                    message=(
                        f"Entry {entry.name!r} has owned_by="
                        f"{entry.owned_by!r} which is not in the active "
                        f"agent_type enum: {sorted(allowed_agents)}"
                    ),
                )
            )
    return findings


def load_artifact_manifest(
    project_dir: Path, manifest_path: Path | None = None
) -> tuple[ArtifactManifest | None, list[ManifestLoadFinding]]:
    """Load `templates/artifacts/manifest.yaml` with full validation.

    Returns (manifest, findings). Missing file → (None, []). Parse or
    schema errors → (None, findings). Enum violations → (manifest, findings).
    """
    path = manifest_path or (project_dir / "templates" / "artifacts" / "manifest.yaml")
    if not path.exists():
        return None, []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return None, [
            ManifestLoadFinding(
                code="manifest_schema/parse_error",
                field=None,
                message=f"manifest.yaml failed to parse: {exc}",
            )
        ]
    try:
        manifest = ArtifactManifest.model_validate(raw)
    except ValidationError as exc:
        findings: list[ManifestLoadFinding] = []
        for err in exc.errors():
            loc = err.get("loc", ())
            field_name = loc[-1] if loc else None
            findings.append(
                ManifestLoadFinding(
                    code="manifest_schema/invalid",
                    field=str(field_name) if field_name is not None else None,
                    message=err.get("msg", "manifest.yaml failed schema validation."),
                )
            )
        return None, findings

    enum_findings = _validate_against_enums(manifest, project_dir)
    return manifest, enum_findings
