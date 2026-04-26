"""Tests for `validate_project` event emission (KUI-100).

The validator must accept an optional `EventEmitter` and emit one
`validator_pass` / `validator_fail` event per `check_*` invocation. The
default emitter (when omitted) is a `NullEmitter`, preserving today's
no-events behaviour for batch / unit-test contexts.

See `docs/specs/2026-04-26-v08-handoff.md` §1.2 (kind subdirs) and §2.2
(event payload shape).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from tripwire.core.event_emitter import EventEmitter
from tripwire.core.validator import validate_project


class _RecordingEmitter:
    """Captures every (kind, payload) tuple emitted during a run."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def emit(self, kind: str, payload: Mapping[str, Any]) -> str:
        self.calls.append((kind, dict(payload)))
        return ""


def _seed_project(tmp_path: Path) -> Path:
    """Write a minimal project so `validate_project` doesn't bail early."""
    payload = {
        "name": "Fixture",
        "key_prefix": "FX",
        "description": "fixture",
        "phase": "scoping",
        "next_issue_number": 1,
        "next_session_number": 1,
    }
    (tmp_path / "project.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    for sub in ("issues", "nodes", "sessions"):
        (tmp_path / sub).mkdir(exist_ok=True)
    return tmp_path


def test_validate_project_accepts_no_emitter(tmp_path: Path) -> None:
    """Default invocation (no emitter) must keep working unchanged."""
    project_dir = _seed_project(tmp_path)
    report = validate_project(project_dir)
    assert report.exit_code in {0, 1, 2}


def test_validate_project_emits_event_per_check(tmp_path: Path) -> None:
    project_dir = _seed_project(tmp_path)
    emitter = _RecordingEmitter()
    validate_project(project_dir, emitter=emitter, session_id="cli-validate")

    # Each emit goes to the `validator_runs` subdir.
    assert emitter.calls, "validator emitted nothing"
    assert all(kind == "validator_runs" for kind, _ in emitter.calls)


def test_emitted_payload_has_required_fields(tmp_path: Path) -> None:
    project_dir = _seed_project(tmp_path)
    emitter = _RecordingEmitter()
    validate_project(project_dir, emitter=emitter, session_id="my-sid")

    sample = emitter.calls[0][1]
    for k in ("id", "kind", "fired_at", "session_id", "validator_id"):
        assert k in sample, f"missing {k!r} in payload: {sample}"
    assert sample["session_id"] == "my-sid"
    assert sample["kind"] in {"validator_pass", "validator_fail"}
    assert sample["validator_id"].startswith("v_")


def test_default_session_id_when_omitted(tmp_path: Path) -> None:
    project_dir = _seed_project(tmp_path)
    emitter = _RecordingEmitter()
    validate_project(project_dir, emitter=emitter)

    # A default sentinel session id is used so events still aggregate
    # under a known session subdir.
    assert emitter.calls
    sample = emitter.calls[0][1]
    assert sample["session_id"]


def test_emitter_satisfies_protocol(tmp_path: Path) -> None:
    project_dir = _seed_project(tmp_path)
    emitter: EventEmitter = _RecordingEmitter()
    validate_project(project_dir, emitter=emitter, session_id="proto")
