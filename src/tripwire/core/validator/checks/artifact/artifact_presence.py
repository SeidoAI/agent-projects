"""Session-side artifact presence gated on the manifest's ``produced_at``."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import _load_manifest
from tripwire.models.session import AgentSession


def check_artifact_presence(ctx: ValidationContext) -> list[CheckResult]:
    """Sessions at-or-past `produced_at` must have each required artifact.

    Mirrors `check_issue_artifact_presence` — consults `produced_at` per
    manifest entry rather than gating every artifact at a single status.
    A session that has reached the threshold for one artifact but not for
    another is checked only against the first.

    Applies the artifact_phase → session_status mapping (so
    `produced_at: planning` correctly gates at session.status >= queued)
    and checks both flat `sessions/<sid>/<file>` and nested
    `sessions/<sid>/artifacts/<file>` layouts before reporting missing.
    Fix-hints prefix with the responsible-actor label from `owned_by`.
    """
    from tripwire.core.issue_artifact_store import status_at_or_past
    from tripwire.core.validator._manifest_lookup import (
        actor_prefix,
        find_artifact_on_disk,
        phase_to_session_status,
    )

    manifest, _ = _load_manifest(ctx)
    if manifest is None:
        return []

    results: list[CheckResult] = []
    for entity in ctx.sessions:
        session: AgentSession = entity.model
        session_dir = ctx.project_dir / paths.SESSIONS_DIR / session.id
        for entry in manifest.artifacts:
            if not entry.required:
                continue
            threshold = phase_to_session_status(entry.produced_at)
            if not status_at_or_past(
                str(session.status),
                threshold,
                ctx.project_dir,
                enum_name="session_status",
            ):
                continue
            if find_artifact_on_disk(session_dir, entry.file) is not None:
                continue
            prefix = actor_prefix(entry)
            results.append(
                CheckResult(
                    code="artifact/missing",
                    severity="error",
                    file=entity.rel_path,
                    field="artifacts",
                    message=(
                        f"Session {session.id!r} ({session.status}) has reached "
                        f"{entry.produced_at!r} but is missing required artifact "
                        f"{entry.file!r}."
                    ),
                    fix_hint=(
                        f"{prefix}write {paths.SESSIONS_DIR}/{session.id}/{entry.file}."
                    ),
                )
            )
    return results
