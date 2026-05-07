"""End-to-end integration smoke for the v0.9 deviation JIT prompts.

Drives a fixture project through ``fire_jit_prompt_event(event="session.complete")``
under scenarios that fire each of the five deviation JIT prompts, then
verifies:

  - Each fire is recorded as a JSON event under
    ``.tripwire/events/jit_prompt_firings/<sid>/``.
  - Acks via ``ctx.ack_path(...)`` (the same path
    ``tripwire test-jit-prompt --ack`` would write to) suppress
    re-firing on the next ``fire_jit_prompt_event`` call.
  - JIT prompts whose pattern isn't present stay silent.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml

from tripwire._internal.jit_prompts import fire_jit_prompt_event
from tripwire.core.session_cost import CostBreakdown


def _seed_project(project_dir: Path, *, phase: str = "executing") -> None:
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "deviation-fixture",
                "key_prefix": "DEV",
                "phase": phase,
                "next_issue_number": 1,
                "next_session_number": 1,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    for sub in ("issues", "nodes", "sessions"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)


def _seed_session(
    project_dir: Path,
    session_id: str,
    *,
    key_files: list[str] | None = None,
    log_path: str | None = None,
) -> None:
    sdir = project_dir / "sessions" / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    body: dict = {
        "id": session_id,
        "name": f"Session {session_id}",
        "agent": "backend-coder",
        "issues": [],
        "key_files": key_files or [],
        "repos": [{"repo": "SeidoAI/demo", "base_branch": "main"}],
    }
    if log_path is not None:
        body["runtime_state"] = {"log_path": log_path, "worktrees": []}
    (sdir / "session.yaml").write_text(
        "---\n" + yaml.safe_dump(body, sort_keys=False) + "---\n",
        encoding="utf-8",
    )


def _seed_issue(
    project_dir: Path,
    issue_id: str,
    *,
    status: str,
    labels: list[str] | None = None,
) -> None:
    idir = project_dir / "issues" / issue_id
    idir.mkdir(parents=True, exist_ok=True)
    body = {
        "id": issue_id,
        "title": f"Issue {issue_id}",
        "priority": "medium",
        "executor": "ai",
        "verifier": "required",
        "status": status,
        "labels": labels or [],
    }
    (idir / "issue.yaml").write_text(
        "---\n" + yaml.safe_dump(body, sort_keys=False) + "---\n",
        encoding="utf-8",
    )


def _seed_pm_response(project_dir: Path, session_id: str, items: list[dict]) -> None:
    artifacts = project_dir / "sessions" / session_id / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "pm-response.yaml").write_text(
        yaml.safe_dump(
            {"read_at": "2026-05-01", "read_by": "pm", "items": items},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _ack(project_dir: Path, jit_prompt_id: str, session_id: str) -> Path:
    """Write a substantive ack marker so ``is_acknowledged`` returns True."""
    marker = project_dir / ".tripwire" / "acks" / f"{jit_prompt_id}-{session_id}.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fix_commits": ["abcd1234"]}), encoding="utf-8")
    return marker


def _firings_for(project_dir: Path, session_id: str, prompt_id: str) -> list[dict]:
    fdir = project_dir / ".tripwire" / "events" / "jit_prompt_firings" / session_id
    if not fdir.is_dir():
        return []
    out: list[dict] = []
    for path in sorted(fdir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("jit_prompt_id") == prompt_id:
            out.append(payload)
    return out


# ---------- phase-transition (B4) -----------------------------------------


def test_phase_transition_fires_on_open_prev_phase_issue(tmp_path: Path) -> None:
    _seed_project(tmp_path, phase="reviewing")
    _seed_session(tmp_path, "alpha")
    _seed_issue(tmp_path, "DEV-1", status="executing", labels=["phase:executing"])

    result = fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="alpha"
    )

    assert any(jit_prompt_id == "phase-transition" for jit_prompt_id, _ in result.fires)
    assert _firings_for(tmp_path, "alpha", "phase-transition")
    assert result.blocked is True


def test_phase_transition_silent_when_clean(tmp_path: Path) -> None:
    _seed_project(tmp_path, phase="reviewing")
    _seed_session(tmp_path, "alpha")
    _seed_issue(tmp_path, "DEV-1", status="completed", labels=["phase:executing"])

    result = fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="alpha"
    )
    assert not any(
        jit_prompt_id == "phase-transition" for jit_prompt_id, _ in result.fires
    )


# ---------- followups-not-filed (B5) --------------------------------------


def test_followups_not_filed_fires_on_missing_issue(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha")
    _seed_pm_response(
        tmp_path,
        "alpha",
        [
            {
                "quote_excerpt": "x",
                "decision": "deferred",
                "follow_up": "DEV-9999",
                "note": "missing",
            }
        ],
    )
    result = fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="alpha"
    )
    assert any(
        jit_prompt_id == "followups-not-filed" for jit_prompt_id, _ in result.fires
    )


def test_followups_not_filed_silent_when_issue_present(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha")
    _seed_issue(tmp_path, "DEV-100", status="queued")
    _seed_pm_response(
        tmp_path,
        "alpha",
        [
            {
                "quote_excerpt": "x",
                "decision": "deferred",
                "follow_up": "DEV-100",
                "note": "filed",
            }
        ],
    )
    result = fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="alpha"
    )
    assert not any(
        jit_prompt_id == "followups-not-filed" for jit_prompt_id, _ in result.fires
    )


# ---------- write-count (B7) ----------------------------------------------


def test_write_count_fires_above_threshold(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    log_path = tmp_path / "claude.log"
    _seed_session(tmp_path, "alpha", log_path=str(log_path))
    # 25 Edit tool calls > default 20.
    log_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "tool_use", "name": "Edit"}]},
                }
            )
            for _ in range(25)
        )
        + "\n",
        encoding="utf-8",
    )
    result = fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="alpha"
    )
    assert any(jit_prompt_id == "write-count" for jit_prompt_id, _ in result.fires)


# ---------- cost-ceiling (B8) ---------------------------------------------


def test_cost_ceiling_fires_above_default(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha", log_path=str(tmp_path / "log.jsonl"))
    bd = CostBreakdown()
    bd.input_usd = 5.50
    with patch(
        "tripwire._internal.jit_prompts.cost_ceiling.compute_session_cost",
        return_value=bd,
    ):
        result = fire_jit_prompt_event(
            project_dir=tmp_path, event="session.complete", session_id="alpha"
        )
    assert any(jit_prompt_id == "cost-ceiling" for jit_prompt_id, _ in result.fires)


# ---------- ack suppresses re-fire ----------------------------------------


def test_ack_suppresses_re_fire(tmp_path: Path) -> None:
    _seed_project(tmp_path, phase="reviewing")
    _seed_session(tmp_path, "alpha")
    _seed_issue(tmp_path, "DEV-1", status="executing", labels=["phase:executing"])

    # First fire — phase-transition fires.
    result1 = fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="alpha"
    )
    assert any(
        jit_prompt_id == "phase-transition" for jit_prompt_id, _ in result1.fires
    )

    # Ack it.
    _ack(tmp_path, "phase-transition", "alpha")

    # Second fire — phase-transition stays silent.
    result2 = fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="alpha"
    )
    assert not any(
        jit_prompt_id == "phase-transition" for jit_prompt_id, _ in result2.fires
    )


# ---------- self-review never silenced --------------------------------


def test_self_review_always_fires_on_unacked_session(tmp_path: Path) -> None:
    """The self-review JIT prompt stays unconditional — regression check
    that the new should_fire gate didn't silence it."""
    _seed_project(tmp_path)
    _seed_session(tmp_path, "alpha")
    result = fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="alpha"
    )
    assert any(jit_prompt_id == "self-review" for jit_prompt_id, _ in result.fires)
