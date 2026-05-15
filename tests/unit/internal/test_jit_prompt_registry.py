"""Tests for the JIT prompt primitive: base class, context, registry/loader.

KUI-99 — see `docs/specs/2026-04-21-v08-jit_prompts-as-primitive.md` and
`docs/specs/2026-04-26-v08-handoff.md` §1 for the contract this module
implements.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tripwire._internal.jit_prompts import (
    JitPrompt,
    JitPromptContext,
    fire_jit_prompt_event,
)
from tripwire._internal.jit_prompts.loader import load_jit_prompt_registry


def _write_project_yaml(project_dir: Path, jit_prompts: dict | None = None) -> None:
    """Minimal project.yaml so load_project succeeds."""
    body: dict = {
        "name": "fixture",
        "key_prefix": "FIX",
        "base_branch": "main",
        "next_issue_number": 1,
        "next_session_number": 1,
        "phase": "scoping",
    }
    if jit_prompts is not None:
        body["jit_prompts"] = jit_prompts
    (project_dir / "project.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")


def test_jit_prompt_base_class_requires_id_and_fires_on() -> None:
    class Incomplete(JitPrompt):
        pass

    with pytest.raises(TypeError):
        Incomplete()


def test_jit_prompt_context_ack_path_layout(tmp_path: Path) -> None:
    ctx = JitPromptContext(
        project_dir=tmp_path,
        session_id="v08-x",
        project_id="proj",
    )
    ack = ctx.ack_path("self-review")
    # v0.13.1: marker name is `<workflow>-<sid>-<prompt>.json`.
    assert (
        ack == tmp_path / ".tripwire" / "acks" / "coding-session-v08-x-self-review.json"
    )


def test_jit_prompt_context_variation_index_deterministic(tmp_path: Path) -> None:
    ctx_a = JitPromptContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    ctx_b = JitPromptContext(
        project_dir=tmp_path, session_id="alpha", project_id="proj"
    )
    ctx_c = JitPromptContext(project_dir=tmp_path, session_id="beta", project_id="proj")
    assert ctx_a.variation_index(3) == ctx_b.variation_index(3)
    # Different session_id likely picks a different variation; assert at
    # least that the function maps deterministically.
    assert isinstance(ctx_c.variation_index(3), int)
    assert 0 <= ctx_a.variation_index(3) < 3


def test_load_jit_prompt_registry_default_includes_self_review(tmp_path: Path) -> None:
    _write_project_yaml(tmp_path)
    registry = load_jit_prompt_registry(tmp_path)
    self_review = [
        prompt
        for prompt in registry.get("session.complete", [])
        if prompt.id == "self-review"
    ]
    assert len(self_review) == 1


def test_load_jit_prompt_registry_disabled_returns_empty(tmp_path: Path) -> None:
    _write_project_yaml(tmp_path, {"enabled": False})
    registry = load_jit_prompt_registry(tmp_path)
    assert registry == {}


def test_load_jit_prompt_registry_opt_out_session_skips_at_fire_time(
    tmp_path: Path,
) -> None:
    _write_project_yaml(tmp_path, {"opt_out": ["fixture-1"]})
    # Session-level opt-out is checked at fire_jit_prompt_event, not load_jit_prompt_registry,
    # so the registry itself still contains the jit_prompts.
    registry = load_jit_prompt_registry(tmp_path)
    assert "session.complete" in registry


def test_fire_jit_prompt_event_first_call_returns_prompt_and_blocks(
    tmp_path: Path,
) -> None:
    _write_project_yaml(tmp_path)
    result = fire_jit_prompt_event(
        project_dir=tmp_path,
        event="session.complete",
        session_id="fixture-1",
    )
    assert result.blocked is True
    assert len(result.prompts) == 1
    assert isinstance(result.prompts[0], str)
    assert result.prompts[0]  # non-empty


def test_fire_jit_prompt_event_writes_event_file(tmp_path: Path) -> None:
    _write_project_yaml(tmp_path)
    fire_jit_prompt_event(
        project_dir=tmp_path,
        event="session.complete",
        session_id="fixture-1",
    )
    fire_dir = tmp_path / ".tripwire" / "events" / "jit_prompt_firings" / "fixture-1"
    files = sorted(fire_dir.glob("*.json"))
    assert len(files) == 1
    assert files[0].name == "0001.json"


def test_fire_jit_prompt_event_disabled_globally(tmp_path: Path) -> None:
    _write_project_yaml(tmp_path, {"enabled": False})
    result = fire_jit_prompt_event(
        project_dir=tmp_path,
        event="session.complete",
        session_id="fixture-1",
    )
    assert result.blocked is False
    assert result.prompts == []


def test_fire_jit_prompt_event_session_opt_out(tmp_path: Path) -> None:
    _write_project_yaml(tmp_path, {"opt_out": ["fixture-1"]})
    result = fire_jit_prompt_event(
        project_dir=tmp_path,
        event="session.complete",
        session_id="fixture-1",
    )
    assert result.blocked is False
    assert result.prompts == []


def test_fire_jit_prompt_event_third_fire_escalates(tmp_path: Path) -> None:
    _write_project_yaml(tmp_path)
    fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="fixture-1"
    )
    fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="fixture-1"
    )
    result = fire_jit_prompt_event(
        project_dir=tmp_path, event="session.complete", session_id="fixture-1"
    )
    assert result.escalated is True
    assert any("--ack" in p for p in result.prompts)
