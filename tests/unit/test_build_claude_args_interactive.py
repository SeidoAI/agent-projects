"""Tests for build_claude_args interactive mode."""

from tripwire.core.spawn_config import build_claude_args
from tripwire.models.spawn import SpawnDefaults


def _defaults() -> SpawnDefaults:
    return SpawnDefaults.model_validate({
        "prompt_template": "hi",
        "system_prompt_append": "sa",
    })


def test_interactive_true_omits_p_flag_and_prompt():
    args = build_claude_args(
        _defaults(),
        prompt=None,
        interactive=True,
        system_append="sa",
        session_id="s1",
        claude_session_id="uuid-1",
    )
    assert "-p" not in args
    assert "hi" not in args
    assert "--session-id" in args
    assert "uuid-1" in args


def test_interactive_false_includes_p_flag_and_prompt():
    args = build_claude_args(
        _defaults(),
        prompt="run this",
        interactive=False,
        system_append="sa",
        session_id="s1",
        claude_session_id="uuid-1",
    )
    assert "-p" in args
    assert "run this" in args


def test_interactive_true_with_non_none_prompt_raises():
    import pytest

    with pytest.raises(ValueError, match="prompt must be None when interactive"):
        build_claude_args(
            _defaults(),
            prompt="don't",
            interactive=True,
            system_append="sa",
            session_id="s1",
            claude_session_id="uuid-1",
        )


def test_interactive_false_with_none_prompt_raises():
    import pytest

    with pytest.raises(ValueError, match="prompt is required"):
        build_claude_args(
            _defaults(),
            prompt=None,
            interactive=False,
            system_append="sa",
            session_id="s1",
            claude_session_id="uuid-1",
        )
