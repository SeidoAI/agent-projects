"""Tests for tripwire.core.codex_args.build_codex_args."""

from __future__ import annotations

import pytest

from tripwire.core.codex_args import build_codex_args
from tripwire.models.spawn import SpawnDefaults


def _defaults(**overrides) -> SpawnDefaults:
    base: dict = {
        "prompt_template": "{plan}",
        "resume_prompt_template": "resume",
        "system_prompt_append": "",
        "invocation": {
            "command": "claude",
            "runtime": "codex",
            "codex_sandbox": "read-only",
        },
        "config": {
            "model": "gpt-5-codex",
            "effort": "medium",
            "provider": "codex",
        },
    }
    for k, v in overrides.items():
        if k in ("invocation", "config"):
            base[k].update(v)
        else:
            base[k] = v
    return SpawnDefaults.model_validate(base)


def test_build_args_first_spawn_shape():
    """codex exec --json -m MODEL -c model_reasoning_effort=… --sandbox …
    PROMPT — exact ordering except for the prompt-positional, which
    must be last."""
    argv = build_codex_args(
        _defaults(),
        prompt="REVIEW THIS PR",
        system_append="",
        session_id="s1",
        codex_session_id="uuid-1",
    )
    assert argv[0] == "codex"
    assert argv[1] == "exec"
    assert "--json" in argv
    # -m MODEL pair
    m_idx = argv.index("-m")
    assert argv[m_idx + 1] == "gpt-5-codex"
    # -c model_reasoning_effort=… is a single arg-string (TOML pair)
    assert any("model_reasoning_effort" in a and '"medium"' in a for a in argv)
    # --sandbox <mode>
    s_idx = argv.index("--sandbox")
    assert argv[s_idx + 1] == "read-only"
    # prompt positional, last
    assert argv[-1] == "REVIEW THIS PR"


def test_build_args_resume_uses_subcommand_with_session_id():
    """`codex exec resume <SESSION_ID>` is a subcommand-with-positional;
    spec called this --resume but codex --help disagrees. Verified
    against codex-cli v0.125.0."""
    argv = build_codex_args(
        _defaults(),
        prompt="resume cue",
        system_append="",
        session_id="s1",
        codex_session_id="codex-uuid-99",
        resume=True,
    )
    assert argv[0] == "codex"
    assert argv[1] == "exec"
    assert argv[2] == "resume"
    assert argv[3] == "codex-uuid-99"


def test_system_append_is_prepended_to_prompt_when_nonempty():
    """Codex has no --append-system-prompt; the workaround per spec
    §3.C is to prepend the system block to the user prompt at invoke."""
    argv = build_codex_args(
        _defaults(),
        prompt="USER PROMPT",
        system_append="SYSTEM RULES BLOCK",
        session_id="s1",
        codex_session_id="uuid-1",
    )
    final = argv[-1]
    # Prepended (system first, prompt second), with a separator that's
    # easy to find in the rendered transcript.
    assert "SYSTEM RULES BLOCK" in final
    assert "USER PROMPT" in final
    assert final.index("SYSTEM RULES BLOCK") < final.index("USER PROMPT")


def test_empty_system_append_does_not_alter_prompt():
    argv = build_codex_args(
        _defaults(),
        prompt="USER PROMPT",
        system_append="",
        session_id="s1",
        codex_session_id="uuid-1",
    )
    assert argv[-1] == "USER PROMPT"


def test_whitespace_only_system_append_skipped():
    argv = build_codex_args(
        _defaults(),
        prompt="P",
        system_append="\n  \n",
        session_id="s1",
        codex_session_id="uuid-1",
    )
    assert argv[-1] == "P"


def test_sandbox_override_threaded_through():
    argv = build_codex_args(
        _defaults(invocation={"codex_sandbox": "danger-full-access"}),
        prompt="P",
        system_append="",
        session_id="s1",
        codex_session_id="uuid-1",
    )
    s_idx = argv.index("--sandbox")
    assert argv[s_idx + 1] == "danger-full-access"


def test_interactive_with_prompt_is_a_programming_error():
    """interactive=True is reserved for a future no-exec path; passing
    a prompt is contradictory — assert the function refuses to build
    a wrong command line silently."""
    with pytest.raises(ValueError):
        build_codex_args(
            _defaults(),
            prompt="X",
            system_append="",
            session_id="s1",
            codex_session_id="uuid-1",
            interactive=True,
        )


def test_non_interactive_without_prompt_is_a_programming_error():
    with pytest.raises(ValueError):
        build_codex_args(
            _defaults(),
            prompt=None,
            system_append="",
            session_id="s1",
            codex_session_id="uuid-1",
        )
