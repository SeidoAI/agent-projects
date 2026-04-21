"""Artifact service — manifest load, session artifact list, approve/reject.

The artifact manifest (``templates/artifacts/manifest.yaml``) enumerates
every artifact a session must produce: file name, template,
produced_at phase, producing agent, owning agent, required flag, and
approval gate. This module exposes:

- :func:`get_manifest` — parse the manifest without enum validation
  (empty manifest on missing file, matching the v0.3 behaviour noted in
  the KUI-22 execution constraints).
- :func:`list_session_artifacts` — cross the manifest with what's
  actually on disk in ``sessions/<sid>/`` (and ``sessions/<sid>/artifacts/``)
  and return one :class:`ArtifactStatus` per manifest entry.
- :func:`get_session_artifact` — load one artifact's body + mtime.
- :func:`approve_artifact` / :func:`reject_artifact` — write an
  ``<name>.approval.yaml`` sidecar next to the session directory. The
  file watcher picks this up naturally via the existing ``sessions/*``
  glob; no new watcher wiring is needed.

Gated-only approvals: approve/reject on an artifact without
``approval_gate: true`` raises :class:`ValueError`. Reject requires a
non-empty feedback string.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from tripwire.core import paths
from tripwire.models.manifest import ArtifactManifest as CoreManifest
from tripwire.ui.services._atomic_write import atomic_write_yaml

logger = logging.getLogger("tripwire.ui.services.artifact_service")


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class ArtifactSpec(BaseModel):
    """One artifact declaration from the manifest.

    Mirrors :class:`tripwire.models.manifest.ArtifactEntry` field-for-field
    so the UI can deserialize the list directly without a second hop. The
    full field set matches the verification checklist requirement
    (``name``, ``file``, ``template``, ``produced_at``, ``produced_by``,
    ``owned_by``, ``required``, ``approval_gate``).
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: str
    file: str
    template: str
    produced_at: str
    produced_by: str = "pm"
    owned_by: str | None = None
    required: bool = True
    approval_gate: bool = False


class ArtifactManifest(BaseModel):
    """Parsed manifest — thin wrapper around a list of :class:`ArtifactSpec`."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    artifacts: list[ArtifactSpec] = Field(default_factory=list)


ArtifactPresence = str  # "present" | "missing" | "approved" | "rejected"


class ApprovalSidecar(BaseModel):
    """Shape of the ``<name>.approval.yaml`` sidecar file."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    approved: bool
    reviewer: str
    reviewed_at: datetime
    feedback: str | None = None


class ArtifactStatus(BaseModel):
    """Manifest spec + on-disk presence + optional approval state.

    ``size_bytes`` / ``last_modified`` are populated only when the file
    exists. ``approval`` is populated only when a sidecar file exists.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    spec: ArtifactSpec
    present: bool
    size_bytes: int | None = None
    last_modified: datetime | None = None
    approval: ApprovalSidecar | None = None


class ArtifactContent(BaseModel):
    """One artifact's loaded body + on-disk metadata.

    Body is intentionally not whitespace-stripped — an artifact file's
    trailing newline and leading indentation are significant (YAML
    frontmatter, fenced code blocks). Only scalar identifier fields go
    through the strip.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    file_path: str
    body: str
    mtime: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sidecar_path(project_dir: Path, session_id: str, name: str) -> Path:
    """Return ``sessions/<sid>/<name>.approval.yaml``.

    The sidecar lives at the session root (not inside ``artifacts/``) so
    the file watcher's default session glob catches it without extra
    filters.
    """
    return paths.session_dir(project_dir, session_id) / f"{name}.approval.yaml"


def _resolve_artifact_file(project_dir: Path, session_id: str, file: str) -> Path:
    """Pick whichever of ``sessions/<sid>/<file>`` or
    ``sessions/<sid>/artifacts/<file>`` actually exists, or the
    ``artifacts/`` path if neither exists (callers expect an absolute
    path even when the file is missing)."""
    sdir = paths.session_dir(project_dir, session_id)
    artifacts_dir = paths.session_artifacts_dir(project_dir, session_id)
    root_candidate = sdir / file
    artifacts_candidate = artifacts_dir / file
    if root_candidate.is_file():
        return root_candidate
    if artifacts_candidate.is_file():
        return artifacts_candidate
    # Prefer the artifacts/ layout for missing files so the UI can
    # surface the expected write location.
    return artifacts_candidate


def _load_sidecar(project_dir: Path, session_id: str, name: str) -> ApprovalSidecar | None:
    path = _sidecar_path(project_dir, session_id, name)
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.warning("approval sidecar yaml error at %s: %s", path, exc)
        return None
    try:
        return ApprovalSidecar.model_validate(raw)
    except ValueError as exc:
        logger.warning("approval sidecar schema error at %s: %s", path, exc)
        return None


def _spec_from_entry(entry: object) -> ArtifactSpec:
    """Coerce a core :class:`ArtifactEntry` into our service-layer DTO."""
    return ArtifactSpec(
        name=entry.name,
        file=entry.file,
        template=entry.template,
        produced_at=entry.produced_at,
        produced_by=entry.produced_by,
        owned_by=entry.owned_by,
        required=entry.required,
        approval_gate=entry.approval_gate,
    )


def _find_spec(manifest: ArtifactManifest, name: str) -> ArtifactSpec:
    for spec in manifest.artifacts:
        if spec.name == name:
            return spec
    raise KeyError(name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_manifest(project_dir: Path) -> ArtifactManifest:
    """Return the parsed manifest, or an empty manifest if the file is missing.

    Schema / YAML errors fall through to an empty manifest with a warning
    — matching the v0.3 behaviour called out in the execution constraints.
    The validator is the gate that surfaces schema errors at scan time;
    the service layer stays read-tolerant.
    """
    path = paths.templates_artifacts_manifest_path(project_dir)
    if not path.is_file():
        return ArtifactManifest(artifacts=[])
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.warning("manifest yaml error at %s: %s", path, exc)
        return ArtifactManifest(artifacts=[])
    try:
        core = CoreManifest.model_validate(raw)
    except ValueError as exc:
        logger.warning("manifest schema error at %s: %s", path, exc)
        return ArtifactManifest(artifacts=[])
    return ArtifactManifest(artifacts=[_spec_from_entry(e) for e in core.artifacts])


def list_session_artifacts(
    project_dir: Path, session_id: str
) -> list[ArtifactStatus]:
    """Return one :class:`ArtifactStatus` per manifest entry.

    Present artifacts carry ``size_bytes`` + ``last_modified``; missing
    ones carry ``None``. Approval sidecars populate the ``approval``
    field regardless of whether the artifact file itself is present.

    Session directories are listed via :mod:`tripwire.core.paths` helpers
    which use ``is_file()`` — symlinks are not dereferenced here because
    the presence check doesn't follow them per the execution constraint.
    """
    manifest = get_manifest(project_dir)
    out: list[ArtifactStatus] = []
    for spec in manifest.artifacts:
        abs_path = _resolve_artifact_file(project_dir, session_id, spec.file)
        # Don't follow symlinks when listing session directories.
        if abs_path.is_symlink():
            present = False
            size_bytes = None
            last_modified = None
        elif abs_path.is_file():
            stat = abs_path.stat()
            present = True
            size_bytes = stat.st_size
            last_modified = datetime.fromtimestamp(stat.st_mtime)
        else:
            present = False
            size_bytes = None
            last_modified = None

        out.append(
            ArtifactStatus(
                spec=spec,
                present=present,
                size_bytes=size_bytes,
                last_modified=last_modified,
                approval=_load_sidecar(project_dir, session_id, spec.name),
            )
        )
    return out


def get_session_artifact(
    project_dir: Path, session_id: str, name: str
) -> ArtifactContent:
    """Return the body + mtime for one manifest artifact.

    Raises:
        FileNotFoundError: if the manifest has no entry named *name* or
            the on-disk file doesn't exist.
    """
    manifest = get_manifest(project_dir)
    try:
        spec = _find_spec(manifest, name)
    except KeyError as exc:
        raise FileNotFoundError(
            f"No manifest entry named {name!r} in project {project_dir}"
        ) from exc

    abs_path = _resolve_artifact_file(project_dir, session_id, spec.file)
    if not abs_path.is_file():
        raise FileNotFoundError(
            f"Artifact file not found for {name!r}: {abs_path}"
        )
    body = abs_path.read_text(encoding="utf-8")
    mtime = datetime.fromtimestamp(abs_path.stat().st_mtime)
    try:
        rel = str(abs_path.relative_to(project_dir))
    except ValueError:
        rel = str(abs_path)
    return ArtifactContent(name=name, file_path=rel, body=body, mtime=mtime)


def _write_sidecar(
    project_dir: Path,
    session_id: str,
    name: str,
    *,
    approved: bool,
    feedback: str | None,
) -> ApprovalSidecar:
    sidecar = ApprovalSidecar(
        approved=approved,
        reviewer="user",
        reviewed_at=datetime.now(),
        feedback=feedback,
    )
    path = _sidecar_path(project_dir, session_id, name)
    data = sidecar.model_dump(mode="json", exclude_none=True)
    atomic_write_yaml(path, data)
    return sidecar


def _require_gate(manifest: ArtifactManifest, name: str) -> ArtifactSpec:
    try:
        spec = _find_spec(manifest, name)
    except KeyError as exc:
        raise ValueError(
            f"No manifest entry named {name!r} — cannot record an approval."
        ) from exc
    if not spec.approval_gate:
        raise ValueError(
            f"Artifact {name!r} has no approval gate configured; "
            f"approve/reject would be a no-op."
        )
    return spec


def approve_artifact(
    project_dir: Path,
    session_id: str,
    name: str,
    feedback: str | None = None,
) -> ArtifactStatus:
    """Record an approval decision for a gated artifact.

    Writes ``sessions/<sid>/<name>.approval.yaml`` with
    ``approved: true`` and returns the refreshed status. No re-engagement
    or orchestration call is made here — that's the UI layer's job
    (v1 approval decisions are purely recorded, per the execution
    constraints).

    Raises:
        ValueError: if *name* isn't in the manifest or isn't gated.
    """
    manifest = get_manifest(project_dir)
    _require_gate(manifest, name)
    _write_sidecar(
        project_dir,
        session_id,
        name,
        approved=True,
        feedback=feedback,
    )
    return _fresh_status(project_dir, session_id, name)


def reject_artifact(
    project_dir: Path,
    session_id: str,
    name: str,
    feedback: str,
) -> ArtifactStatus:
    """Record a rejection for a gated artifact.

    *feedback* must be a non-empty string once stripped — rejecting
    without reason is what happens by accident when the UI forgets to
    collect the textarea input, and the empty-string check here makes
    the omission a 400 instead of a silent decision.

    Raises:
        ValueError: if the artifact isn't gated or feedback is empty.
    """
    if feedback is None or not feedback.strip():
        raise ValueError("Reject requires non-empty feedback.")
    manifest = get_manifest(project_dir)
    _require_gate(manifest, name)
    _write_sidecar(
        project_dir,
        session_id,
        name,
        approved=False,
        feedback=feedback,
    )
    return _fresh_status(project_dir, session_id, name)


def _fresh_status(
    project_dir: Path, session_id: str, name: str
) -> ArtifactStatus:
    """Rebuild a single ArtifactStatus after a sidecar write.

    We rerun the full :func:`list_session_artifacts` and pick out the
    matching entry so the returned status includes the new sidecar
    without duplicating the on-disk probe logic.
    """
    for status in list_session_artifacts(project_dir, session_id):
        if status.spec.name == name:
            return status
    # Should never happen — _require_gate already proved the entry exists.
    raise RuntimeError(
        f"Manifest changed mid-flight: {name!r} disappeared after write."
    )


__all__ = [
    "ApprovalSidecar",
    "ArtifactContent",
    "ArtifactManifest",
    "ArtifactSpec",
    "ArtifactStatus",
    "approve_artifact",
    "get_manifest",
    "get_session_artifact",
    "list_session_artifacts",
    "reject_artifact",
]
