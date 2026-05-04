"""Manifest schema + artifact presence (sessions and issues)."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.enums import SessionStatus
from tripwire.models.manifest import ArtifactManifest
from tripwire.models.session import AgentSession


def _load_manifest(
    ctx: ValidationContext,
) -> tuple[ArtifactManifest | None, list[CheckResult]]:
    """Parse `templates/artifacts/manifest.yaml` via the shared loader.

    Returns (manifest, findings). A missing manifest file is not an error
    (returns `(None, [])`). YAML parse errors, schema violations, and enum
    violations (unknown `produced_at` / `produced_by` / `owned_by`) surface
    as `manifest_schema/*` findings so `check_manifest_schema` can emit them.
    """
    from tripwire.core.manifest_loader import load_artifact_manifest

    manifest_path = paths.templates_artifacts_manifest_path(ctx.project_dir)
    rel = paths.TEMPLATES_ARTIFACTS_MANIFEST
    manifest, load_findings = load_artifact_manifest(ctx.project_dir, manifest_path)
    findings = [
        CheckResult(
            code=f.code,
            severity="error",
            file=rel,
            field=f.field,
            message=f.message,
        )
        for f in load_findings
    ]
    return manifest, findings


def check_manifest_schema(ctx: ValidationContext) -> list[CheckResult]:
    """`templates/artifacts/manifest.yaml` parses and matches the schema.

    Emits `manifest_schema/produced_by_valid` or `manifest_schema/owned_by_valid`
    when those enum-like fields carry an unknown agent type.
    """
    _, findings = _load_manifest(ctx)
    return findings


def check_manifest_phase_ownership_consistent(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """Warn if pm owns an artifact produced during in_progress/in_review.

    The PM agent steers scoping and planning; once a session is in
    `in_progress` or `in_review`, the execution/verification agent owns
    what gets written. A manifest that assigns `owned_by: pm` to such
    artifacts likely encodes the v0.5 bug where the PM wrote files the
    execution agent should have written.
    """
    manifest, _ = _load_manifest(ctx)
    if manifest is None:
        return []
    results: list[CheckResult] = []
    for entry in manifest.artifacts:
        # v0.9.4: canonical "executing" + legacy "in_progress" alias.
        if entry.owned_by == "pm" and entry.produced_at in (
            "executing",
            "in_progress",
            "in_review",
        ):
            results.append(
                CheckResult(
                    code="manifest_schema/phase_ownership_consistent",
                    severity="warning",
                    file=paths.TEMPLATES_ARTIFACTS_MANIFEST,
                    field="owned_by",
                    message=(
                        f"artifact '{entry.name}' owned by pm but produced at "
                        f"{entry.produced_at} — consider ownership by "
                        "execution-agent or verification-agent"
                    ),
                )
            )
    return results


def check_artifact_presence(ctx: ValidationContext) -> list[CheckResult]:
    """Sessions at status=completed must have all required artifacts.

    The terminal-success state is `completed`. If a future release adds a
    distinct post-merge state, extend the predicate below.
    """
    manifest, _ = _load_manifest(ctx)
    if manifest is None:
        return []
    required_files = [a.file for a in manifest.artifacts if a.required]

    results: list[CheckResult] = []
    for entity in ctx.sessions:
        session: AgentSession = entity.model
        if session.status != SessionStatus.COMPLETED:
            continue
        artifacts_dir = paths.session_artifacts_dir(ctx.project_dir, session.id)
        for artifact_file in required_files:
            if not (artifacts_dir / artifact_file).exists():
                results.append(
                    CheckResult(
                        code="artifact/missing",
                        severity="error",
                        file=entity.rel_path,
                        field="artifacts",
                        message=(
                            f"Completed session {session.id!r} is missing required artifact "
                            f"{artifact_file!r}."
                        ),
                        fix_hint=(
                            f"Write {paths.SESSIONS_DIR}/{session.id}/"
                            f"{paths.SESSION_ARTIFACTS_SUBDIR}/{artifact_file}."
                        ),
                    )
                )
    return results


def check_issue_artifact_presence(ctx: ValidationContext) -> list[CheckResult]:
    """Every issue at status ≥ required_at_status must have its artifact file.

    Loads the issue artifact manifest (shipped + project overrides), then for
    each issue checks whether the required files exist once the issue has
    reached the status gate.
    """
    from tripwire.core.issue_artifact_store import (
        load_issue_artifact_manifest,
        status_at_or_past,
    )

    results: list[CheckResult] = []
    try:
        manifest = load_issue_artifact_manifest(ctx.project_dir)
    except FileNotFoundError:
        # Manifest template missing from the installed package — not fatal.
        return results
    except Exception as exc:
        results.append(
            CheckResult(
                code="issue_artifact_manifest/invalid",
                severity="error",
                file="templates/issue_artifacts/manifest.yaml",
                message=f"Failed to load issue artifact manifest: {exc}",
            )
        )
        return results

    for entity in ctx.issues:
        issue = entity.model
        for entry in manifest.artifacts:
            if not entry.required:
                continue
            if not status_at_or_past(
                issue.status, entry.required_at_status, ctx.project_dir
            ):
                continue
            artifact_path = ctx.project_dir / "issues" / issue.id / entry.file
            if artifact_path.is_file():
                continue
            results.append(
                CheckResult(
                    code="issue_artifact/missing",
                    severity="error",
                    file=f"issues/{issue.id}/{entry.file}",
                    message=(
                        f"Issue {issue.id!r} ({issue.status}) has reached "
                        f"{entry.required_at_status!r} but is missing "
                        f"required artifact {entry.file!r}."
                    ),
                    fix_hint=(
                        f"Write issues/{issue.id}/{entry.file} from {entry.template}."
                    ),
                )
            )
    return results
