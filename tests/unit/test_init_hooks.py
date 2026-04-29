"""Tests for KUI-110 Phase 1.3 — `tripwire init` plants `.claude/settings.json`.

Smoke test that `tripwire init` runs the same `install_settings_into`
helper used by `hooks install` so a fresh project gets the edit-time
hook from day zero.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.init import init_cmd


def _run_init(target: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        init_cmd,
        [
            str(target),
            "--non-interactive",
            "--name",
            "demo",
            "--key-prefix",
            "DEM",
            "--base-branch",
            "main",
            "--no-git",
            "--no-remote",
        ],
    )
    assert result.exit_code == 0, result.output


def test_init_writes_claude_settings_with_hook_entry(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _run_init(target)

    settings_path = target / ".claude" / "settings.json"
    assert settings_path.is_file(), "init should drop .claude/settings.json"
    settings = json.loads(settings_path.read_text())

    post_tool_use = settings.get("hooks", {}).get("PostToolUse", [])
    commands = []
    for block in post_tool_use:
        for h in block.get("hooks", []):
            commands.append(h.get("command"))
    assert any(
        "tripwire hook validate-on-edit" in (c or "") for c in commands
    ), f"expected validate-on-edit hook in {commands}"
