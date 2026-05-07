"""Tests for the followups-not-filed JIT prompt (KUI-139 / B5).

Fires on ``session.complete`` when the session's ``pm-response.yaml``
declares ``decision: deferred`` items with ``follow_up: KUI-XXX`` but
the referenced issue isn't on disk. Enforces the user's standing rule
"Follow-ups are immediate, not deferred".
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from tripwire._internal.jit_prompts import JitPromptContext
from tripwire._internal.jit_prompts.followups_not_filed import (
    _VARIATIONS,
    FollowupsNotFiledJitPrompt,
    _missing_followups,
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


def _seed_session(project_dir: Path, session_id: str) -> None:
    sdir = project_dir / "sessions" / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    body = {
        "id": session_id,
        "name": f"Session {session_id}",
        "agent": "backend-coder",
        "issues": [],
        "repos": [{"repo": "SeidoAI/demo", "base_branch": "main"}],
    }
    (sdir / "session.yaml").write_text(
        "---\n" + yaml.safe_dump(body, sort_keys=False) + "---\n",
        encoding="utf-8",
    )


def _seed_issue(project_dir: Path, issue_id: str) -> None:
    idir = project_dir / "issues" / issue_id
    idir.mkdir(parents=True, exist_ok=True)
    body = {
        "id": issue_id,
        "title": f"Follow-up {issue_id}",
        "priority": "medium",
        "executor": "ai",
        "verifier": "required",
        "status": "queued",
        "labels": [],
    }
    (idir / "issue.yaml").write_text(
        "---\n" + yaml.safe_dump(body, sort_keys=False) + "---\n",
        encoding="utf-8",
    )


def _seed_pm_response(
    project_dir: Path,
    session_id: str,
    items: list[dict],
) -> None:
    sdir = project_dir / "sessions" / session_id / "artifacts"
    sdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "read_at": "2026-05-01T00:00:00",
        "read_by": "pm",
        "items": items,
    }
    (sdir / "pm-response.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )


def _ctx(tmp_path: Path, session_id: str = "alpha") -> JitPromptContext:
    return JitPromptContext(
        project_dir=tmp_path,
        session_id=session_id,
        project_id="demo",
    )


def test_class_attrs() -> None:
    tw = FollowupsNotFiledJitPrompt()
    assert tw.id == "followups-not-filed"
    assert tw.fires_on == "session.complete"
    assert tw.blocks is True


def test_three_variations_present() -> None:
    assert len(_VARIATIONS) == 3
    for v in _VARIATIONS:
        assert "--ack" in v
        assert "follow" in v.lower()


def test_silent_when_pm_response_absent(tmp_path: Path) -> None:
    """No pm-response.yaml → silent (PM hasn't responded yet)."""
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha")
    tw = FollowupsNotFiledJitPrompt()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_silent_when_no_deferred_items(tmp_path: Path) -> None:
    """pm-response with only `accepted` decisions → silent."""
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha")
    _seed_pm_response(
        tmp_path,
        "alpha",
        items=[
            {"quote_excerpt": "x", "decision": "accepted", "note": "noted"},
        ],
    )
    tw = FollowupsNotFiledJitPrompt()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_silent_when_followup_issue_exists(tmp_path: Path) -> None:
    """Deferred + follow_up + issue on disk → silent."""
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha")
    _seed_issue(tmp_path, "DEM-100")
    _seed_pm_response(
        tmp_path,
        "alpha",
        items=[
            {
                "quote_excerpt": "needs follow-up",
                "decision": "deferred",
                "follow_up": "DEM-100",
                "note": "see DEM-100",
            },
        ],
    )
    tw = FollowupsNotFiledJitPrompt()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_fires_when_followup_issue_missing(tmp_path: Path) -> None:
    """Deferred + follow_up but no issue on disk → fires."""
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha")
    _seed_pm_response(
        tmp_path,
        "alpha",
        items=[
            {
                "quote_excerpt": "x",
                "decision": "deferred",
                "follow_up": "DEM-9999",
                "note": "TBD",
            },
        ],
    )
    tw = FollowupsNotFiledJitPrompt()
    assert tw.should_fire(_ctx(tmp_path)) is True


def test_missing_followups_lists_unfiled_ids(tmp_path: Path) -> None:
    """The helper returns the set of declared-but-missing IDs."""
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha")
    _seed_issue(tmp_path, "DEM-200")
    _seed_pm_response(
        tmp_path,
        "alpha",
        items=[
            {
                "quote_excerpt": "x",
                "decision": "deferred",
                "follow_up": "DEM-200",
                "note": "filed",
            },
            {
                "quote_excerpt": "y",
                "decision": "deferred",
                "follow_up": "DEM-201",
                "note": "missing",
            },
            {
                "quote_excerpt": "z",
                "decision": "deferred",
                "follow_up": "DEM-202",
                "note": "missing",
            },
        ],
    )
    missing = _missing_followups(tmp_path, "alpha")
    assert missing == {"DEM-201", "DEM-202"}


def test_silent_when_session_dir_missing(tmp_path: Path) -> None:
    """Unknown session id → silent (no spurious fire)."""
    _seed_project(tmp_path)
    tw = FollowupsNotFiledJitPrompt()
    assert tw.should_fire(_ctx(tmp_path, session_id="ghost")) is False


def test_fire_returns_one_of_the_variations(tmp_path: Path) -> None:
    tw = FollowupsNotFiledJitPrompt()
    prompt = tw.fire(_ctx(tmp_path))
    assert prompt in _VARIATIONS


def test_acknowledged_with_substantive_marker(tmp_path: Path) -> None:
    tw = FollowupsNotFiledJitPrompt()
    ctx = _ctx(tmp_path)
    marker = ctx.ack_path("followups-not-filed")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fix_commits": ["abc1234"]}), encoding="utf-8")
    assert tw.is_acknowledged(ctx) is True


def test_acknowledged_empty_marker_rejected(tmp_path: Path) -> None:
    tw = FollowupsNotFiledJitPrompt()
    ctx = _ctx(tmp_path)
    marker = ctx.ack_path("followups-not-filed")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}", encoding="utf-8")
    assert tw.is_acknowledged(ctx) is False
