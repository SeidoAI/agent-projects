"""Tests for the stopped-to-ask tripwire (KUI-140 / B6).

Fires on ``session.complete`` if the session plan declares a
``## Stop and ask`` section but the session log shows no agent comment
invoking the path AND committed files extend outside the
``key_files`` declared in session.yaml. The signal is
"scope-creep without surfacing it".
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from tripwire._internal.tripwires import TripwireContext
from tripwire._internal.tripwires.stopped_to_ask import (
    StoppedToAskTripwire,
    _VARIATIONS,
    _plan_has_stop_and_ask,
    _scope_creep,
    _stop_ask_signalled,
)


def _seed_project(project_dir: Path) -> None:
    project_yaml = {
        "name": "demo-project",
        "key_prefix": "DEM",
        "phase": "executing",
        "repos": {"SeidoAI/demo": {"local": "."}},
    }
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(project_yaml, sort_keys=False), encoding="utf-8"
    )


def _seed_session(
    project_dir: Path,
    session_id: str,
    *,
    key_files: list[str],
) -> None:
    sdir = project_dir / "sessions" / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    body = {
        "id": session_id,
        "name": f"Session {session_id}",
        "agent": "backend-coder",
        "issues": [],
        "key_files": key_files,
        "repos": [{"repo": "SeidoAI/demo", "base_branch": "main"}],
    }
    (sdir / "session.yaml").write_text(
        "---\n" + yaml.safe_dump(body, sort_keys=False) + "---\n",
        encoding="utf-8",
    )


def _seed_plan(project_dir: Path, session_id: str, body: str) -> None:
    artifacts = project_dir / "sessions" / session_id / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "plan.md").write_text(body, encoding="utf-8")


def _seed_comment(
    project_dir: Path,
    session_id: str,
    name: str,
    body: dict,
) -> None:
    comments_dir = project_dir / "sessions" / session_id / "comments"
    comments_dir.mkdir(parents=True, exist_ok=True)
    (comments_dir / f"{name}.yaml").write_text(
        yaml.safe_dump(body, sort_keys=False), encoding="utf-8"
    )


def _ctx(tmp_path: Path, session_id: str = "alpha") -> TripwireContext:
    return TripwireContext(
        project_dir=tmp_path,
        session_id=session_id,
        project_id="demo",
    )


def test_class_attrs() -> None:
    tw = StoppedToAskTripwire()
    assert tw.id == "stopped-to-ask"
    assert tw.fires_on == "session.complete"
    assert tw.blocks is True


def test_three_variations_present() -> None:
    assert len(_VARIATIONS) == 3
    for v in _VARIATIONS:
        assert "--ack" in v
        assert "stop" in v.lower()


def test_plan_has_stop_and_ask_detects_h2_section() -> None:
    assert _plan_has_stop_and_ask("## Stop and ask\n- if X happens, stop\n") is True
    # case-insensitive variant
    assert _plan_has_stop_and_ask("## stop and ASK\nbody\n") is True


def test_plan_has_stop_and_ask_negative() -> None:
    assert _plan_has_stop_and_ask("## Steps\nbody\n") is False
    assert _plan_has_stop_and_ask("") is False


def test_scope_creep_detects_outside_files() -> None:
    """Touched files including any not under any key_files entry → True."""
    key = ["src/foo/", "src/bar.py"]
    assert _scope_creep(["src/foo/x.py"], key) is False
    assert _scope_creep(["src/bar.py"], key) is False
    assert _scope_creep(["src/foo/x.py", "src/baz/y.py"], key) is True


def test_scope_creep_empty_key_files_treats_anything_as_creep() -> None:
    """If session.yaml lacks key_files, any touched file is creep."""
    assert _scope_creep(["src/x.py"], []) is True
    assert _scope_creep([], []) is False


def test_stop_ask_signalled_via_comment(tmp_path: Path) -> None:
    """Comment naming stop-and-ask in body or kind counts as signalled."""
    _seed_comment(
        tmp_path,
        "alpha",
        "001",
        {
            "kind": "stop_and_ask",
            "body": "I hit a corner case — please decide between A and B.",
        },
    )
    assert _stop_ask_signalled(tmp_path, "alpha") is True


def test_stop_ask_signalled_negative_when_no_comments(tmp_path: Path) -> None:
    assert _stop_ask_signalled(tmp_path, "alpha") is False


def test_should_fire_clean_session(tmp_path: Path) -> None:
    """Plan has no Stop-and-ask section → silent."""
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha", key_files=["src/foo/"])
    _seed_plan(tmp_path, "alpha", "## Steps\nbody\n")
    tw = StoppedToAskTripwire()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_should_fire_when_scope_creep_no_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan has Stop-and-ask, scope creep, no signal → fires."""
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha", key_files=["src/foo/"])
    _seed_plan(tmp_path, "alpha", "## Stop and ask\n- if X, stop\n")

    # Monkeypatch the "touched files" provider to simulate scope creep.
    from tripwire._internal.tripwires import stopped_to_ask

    monkeypatch.setattr(
        stopped_to_ask,
        "_session_touched_files",
        lambda project_dir, session_id: ["src/foo/x.py", "src/baz/y.py"],
    )

    tw = StoppedToAskTripwire()
    assert tw.should_fire(_ctx(tmp_path)) is True


def test_should_fire_silent_when_signal_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan has Stop-and-ask + creep + comment → silent."""
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha", key_files=["src/foo/"])
    _seed_plan(tmp_path, "alpha", "## Stop and ask\n- if X, stop\n")
    _seed_comment(
        tmp_path,
        "alpha",
        "001",
        {"kind": "stop_and_ask", "body": "blocked on Y, please decide?"},
    )
    from tripwire._internal.tripwires import stopped_to_ask

    monkeypatch.setattr(
        stopped_to_ask,
        "_session_touched_files",
        lambda project_dir, session_id: ["src/foo/x.py", "src/baz/y.py"],
    )
    tw = StoppedToAskTripwire()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_fire_returns_one_of_the_variations(tmp_path: Path) -> None:
    tw = StoppedToAskTripwire()
    prompt = tw.fire(_ctx(tmp_path))
    assert prompt in _VARIATIONS


def test_acknowledged_with_substantive_marker(tmp_path: Path) -> None:
    tw = StoppedToAskTripwire()
    ctx = _ctx(tmp_path)
    marker = ctx.ack_path("stopped-to-ask")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fix_commits": ["abc1234"]}), encoding="utf-8")
    assert tw.is_acknowledged(ctx) is True
