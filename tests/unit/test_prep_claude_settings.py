"""Tests for KUI-110 Phase 1.4 — `install_claude_settings` helper.

Plain helper test: writes settings.json into a tmp worktree dir and
asserts the validate-on-edit hook is wired in. The end-to-end spawn
test surface is covered by other tests in this directory; this one
just locks in that the helper is callable + idempotent + writes the
expected shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from tripwire.runtimes.prep import install_claude_settings


def test_install_claude_settings_writes_settings(tmp_path: Path) -> None:
    install_claude_settings(worktree=tmp_path)

    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.is_file()
    settings = json.loads(settings_path.read_text())
    commands = []
    for block in settings["hooks"]["PostToolUse"]:
        for h in block.get("hooks", []):
            commands.append(h.get("command"))
    assert any("tripwire hook validate-on-edit" in (c or "") for c in commands)


def test_install_claude_settings_is_idempotent(tmp_path: Path) -> None:
    install_claude_settings(worktree=tmp_path)
    first = (tmp_path / ".claude" / "settings.json").read_text()

    install_claude_settings(worktree=tmp_path)
    second = (tmp_path / ".claude" / "settings.json").read_text()

    assert json.loads(first) == json.loads(second)
