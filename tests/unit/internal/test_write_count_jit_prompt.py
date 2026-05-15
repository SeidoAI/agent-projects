"""Tests for the write-count JIT prompt (KUI-141 / B7).

Fires on ``session.complete`` when the count of file-edit tool
invocations in the session's claude log exceeds a threshold (default
20). Per-project override via ``project.yaml.jit_prompts.extra`` for an
entry with ``id: write-count`` and ``params: {threshold: N}``.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from tripwire._internal.jit_prompts import JitPromptContext
from tripwire._internal.jit_prompts.write_count import (
    _VARIATIONS,
    DEFAULT_WRITE_COUNT_THRESHOLD,
    WriteCountJitPrompt,
    _count_writes,
    _read_threshold,
)

WRITE_TOOLS = ("Edit", "Write", "NotebookEdit")


def _seed_project(project_dir: Path, *, extras: list[dict] | None = None) -> None:
    project_yaml = {
        "name": "demo-project",
        "key_prefix": "DEM",
        "phase": "executing",
        "repos": {"SeidoAI/demo": {"local": "."}},
    }
    if extras is not None:
        project_yaml["jit_prompts"] = {"extra": extras}
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(project_yaml, sort_keys=False), encoding="utf-8"
    )


def _seed_session_with_log(
    project_dir: Path,
    session_id: str,
    *,
    write_count: int,
) -> Path:
    """Write a minimal session.yaml + a synthetic claude stream-json log.

    Returns the absolute path to the log so the runtime_state.log_path
    field can carry it.
    """
    sdir = project_dir / "instances" / "sessions" / session_id
    sdir.mkdir(parents=True, exist_ok=True)
    log_path = sdir / "claude.log"

    body = {
        "id": session_id,
        "name": f"Session {session_id}",
        "agent": "backend-coder",
        "issues": [],
        "repos": [{"repo": "SeidoAI/demo", "base_branch": "main"}],
        "runtime_state": {"log_path": str(log_path), "worktrees": []},
    }
    (sdir / "session.yaml").write_text(
        "---\n" + yaml.safe_dump(body, sort_keys=False) + "---\n",
        encoding="utf-8",
    )

    lines = []
    for i in range(write_count):
        tool_name = WRITE_TOOLS[i % len(WRITE_TOOLS)]
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "model": "claude-opus-4-7",
                        "content": [
                            {"type": "tool_use", "name": tool_name, "input": {}}
                        ],
                    },
                }
            )
        )
    # A non-write tool call shouldn't count.
    lines.append(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-7",
                    "content": [{"type": "tool_use", "name": "Read", "input": {}}],
                },
            }
        )
    )
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def _ctx(tmp_path: Path, session_id: str = "alpha") -> JitPromptContext:
    return JitPromptContext(
        project_dir=tmp_path,
        session_id=session_id,
        project_id="demo",
    )


def test_class_attrs() -> None:
    tw = WriteCountJitPrompt()
    assert tw.id == "write-count"
    assert tw.fires_on == "session.complete"
    assert tw.blocks is True


def test_default_threshold_is_20() -> None:
    assert DEFAULT_WRITE_COUNT_THRESHOLD == 20


def test_three_variations_present() -> None:
    assert len(_VARIATIONS) == 3
    for v in _VARIATIONS:
        assert "--ack" in v
        assert "validate" in v.lower() or "write" in v.lower()


def test_count_writes_only_counts_edit_tools(tmp_path: Path) -> None:
    """Only Edit/Write/NotebookEdit tool_use events count."""
    log_lines = [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "name": "Edit"}],
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "name": "Read"}],
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "name": "Write"}],
                },
            }
        ),
    ]
    log_path = tmp_path / "_write_count_test.jsonl"
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    assert _count_writes(log_path) == 2


def test_count_writes_missing_log_returns_zero(tmp_path: Path) -> None:
    assert _count_writes(tmp_path / "nope.log") == 0


def test_should_fire_under_threshold(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    _seed_session_with_log(tmp_path, "alpha", write_count=5)
    tw = WriteCountJitPrompt()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_should_fire_above_default_threshold(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    _seed_session_with_log(
        tmp_path, "alpha", write_count=DEFAULT_WRITE_COUNT_THRESHOLD + 5
    )
    tw = WriteCountJitPrompt()
    assert tw.should_fire(_ctx(tmp_path)) is True


def test_per_project_threshold_override_respected(tmp_path: Path) -> None:
    """Per-project override via jit_prompts.extra.params.threshold."""
    _seed_project(
        tmp_path,
        extras=[
            {
                "id": "write-count",
                "fires_on": "session.complete",
                "class": (
                    "tripwire._internal.jit_prompts.write_count.WriteCountJitPrompt"
                ),
                "params": {"threshold": 5},
            }
        ],
    )
    _seed_session_with_log(tmp_path, "alpha", write_count=10)
    tw = WriteCountJitPrompt()
    # 10 > 5 (override) → fires
    assert tw.should_fire(_ctx(tmp_path)) is True


def test_per_project_threshold_override_silent_below(tmp_path: Path) -> None:
    _seed_project(
        tmp_path,
        extras=[
            {
                "id": "write-count",
                "fires_on": "session.complete",
                "class": (
                    "tripwire._internal.jit_prompts.write_count.WriteCountJitPrompt"
                ),
                "params": {"threshold": 100},
            }
        ],
    )
    _seed_session_with_log(tmp_path, "alpha", write_count=50)
    tw = WriteCountJitPrompt()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_read_threshold_default_when_no_extra(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    assert _read_threshold(tmp_path) == DEFAULT_WRITE_COUNT_THRESHOLD


def test_read_threshold_uses_extra_params(tmp_path: Path) -> None:
    _seed_project(
        tmp_path,
        extras=[
            {
                "id": "write-count",
                "fires_on": "session.complete",
                "class": (
                    "tripwire._internal.jit_prompts.write_count.WriteCountJitPrompt"
                ),
                "params": {"threshold": 7},
            }
        ],
    )
    assert _read_threshold(tmp_path) == 7


def test_silent_when_log_path_missing(tmp_path: Path) -> None:
    """No runtime_state.log_path → silent (session never spawned)."""
    _seed_project(tmp_path)
    sdir = tmp_path / "instances" / "sessions" / "alpha"
    sdir.mkdir(parents=True)
    body = {
        "id": "alpha",
        "name": "Alpha",
        "agent": "backend-coder",
        "issues": [],
        "repos": [{"repo": "SeidoAI/demo", "base_branch": "main"}],
    }
    (sdir / "session.yaml").write_text(
        "---\n" + yaml.safe_dump(body, sort_keys=False) + "---\n",
        encoding="utf-8",
    )
    tw = WriteCountJitPrompt()
    assert tw.should_fire(_ctx(tmp_path)) is False


def test_acknowledged_with_substantive_marker(tmp_path: Path) -> None:
    tw = WriteCountJitPrompt()
    ctx = _ctx(tmp_path)
    marker = ctx.ack_path("write-count")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fix_commits": ["abc1234"]}), encoding="utf-8")
    assert tw.is_acknowledged(ctx) is True


def test_fire_returns_one_of_the_variations(tmp_path: Path) -> None:
    tw = WriteCountJitPrompt()
    prompt = tw.fire(_ctx(tmp_path))
    assert prompt in _VARIATIONS
