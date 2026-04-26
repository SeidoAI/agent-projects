"""Tests for the runtime registry."""

import pytest


def test_registry_has_subprocess_and_manual():
    from tripwire.runtimes import RUNTIMES

    assert "claude" in RUNTIMES
    assert "manual" in RUNTIMES


def test_get_runtime_unknown_raises_with_valid_options():
    from tripwire.runtimes import get_runtime

    with pytest.raises(ValueError) as exc_info:
        get_runtime("tmux")
    assert "tmux" in str(exc_info.value)
    assert "claude" in str(exc_info.value)
    assert "manual" in str(exc_info.value)


def test_attach_exec_and_attach_instruction_are_distinct_types():
    from tripwire.runtimes.base import AttachExec, AttachInstruction

    e = AttachExec(argv=["tail", "-f", "/tmp/x.log"])
    i = AttachInstruction(message="run this yourself")
    assert e.argv == ["tail", "-f", "/tmp/x.log"]
    assert i.message == "run this yourself"
    assert not isinstance(e, AttachInstruction)
    assert not isinstance(i, AttachExec)
