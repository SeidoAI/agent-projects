"""Tests for `reject_artifact` event emission (KUI-100).

`reject_artifact` accepts an optional `EventEmitter`; when supplied, one
`artifact_rejected` event is emitted into the `rejections/` subdir.
Default `NullEmitter` preserves today's silent behaviour.

See `docs/specs/2026-04-26-v08-handoff.md` §1.2.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from tripwire.ui.services.artifact_service import reject_artifact


class _RecordingEmitter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def emit(self, kind: str, payload: Mapping[str, Any]) -> str:
        self.calls.append((kind, dict(payload)))
        return ""


def _write_manifest(project_dir: Path, artifacts: list[dict[str, Any]]) -> None:
    path = project_dir / "templates" / "artifacts" / "manifest.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"artifacts": artifacts}, sort_keys=False))


@pytest.fixture
def gated_project(tmp_path: Path) -> tuple[Path, str]:
    """Project + session + manifest with a gated `plan` artifact."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "Fixture",
                "key_prefix": "FX",
                "phase": "scoping",
                "next_issue_number": 1,
                "next_session_number": 1,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    for sub in ("issues", "nodes", "sessions"):
        (project_dir / sub).mkdir(exist_ok=True)
    sid = "s1"
    (project_dir / "sessions" / sid).mkdir()

    _write_manifest(
        project_dir,
        [
            {
                "name": "plan",
                "file": "plan.md",
                "template": "plan.md.j2",
                "produced_at": "planning",
                "produced_by": "pm",
                "owned_by": "pm",
                "required": True,
                "approval_gate": True,
            },
        ],
    )
    return project_dir, sid


def test_reject_artifact_emits_event(
    gated_project: tuple[Path, str],
) -> None:
    project_dir, sid = gated_project
    emitter = _RecordingEmitter()
    reject_artifact(
        project_dir,
        sid,
        "plan",
        feedback="scope too broad — split auth changes",
        emitter=emitter,
        session_id=sid,
    )
    assert any(kind == "rejections" for kind, _ in emitter.calls)
    payload = next(p for k, p in emitter.calls if k == "rejections")
    for key in ("id", "kind", "fired_at", "session_id", "artifact"):
        assert key in payload, f"missing {key!r} in {payload}"
    assert payload["kind"] == "artifact_rejected"
    assert payload["session_id"] == sid
    assert payload["artifact"] == "plan"
    assert payload["feedback_excerpt"]


def test_reject_artifact_default_emitter_no_op(
    gated_project: tuple[Path, str],
) -> None:
    """Existing call sites (no emitter passed) keep working unchanged."""
    project_dir, sid = gated_project
    reject_artifact(project_dir, sid, "plan", feedback="too thin")
    # No assertion needed — the call must simply not raise.


def test_reject_artifact_emitter_kw_only(
    gated_project: tuple[Path, str],
) -> None:
    """`emitter` is keyword-only — the legacy positional 4-arg shape is
    unchanged so existing callers keep compiling."""
    project_dir, sid = gated_project
    # Positional args: project_dir, session_id, name, feedback
    reject_artifact(project_dir, sid, "plan", "concise feedback")
