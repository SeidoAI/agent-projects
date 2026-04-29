"""Tests for `tripwire hooks install` retrofit command (KUI-110 Phase 1.5).

This is the operator-facing verb used to add (or upgrade) the
PostToolUse hook entry in `<project>/.claude/settings.json` for an
existing project. Plain `tripwire init` and `tripwire session spawn`
plant the same hook on new flows.

The merge logic shared with init/spawn is exercised through this CLI
surface: idempotent without `--force`, overwrite with `--force`.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from tripwire.cli.main import cli


def _project(project_dir: Path) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "fixture",
                "key_prefix": "FIX",
                "base_branch": "main",
                "next_issue_number": 1,
                "next_session_number": 1,
            }
        ),
        encoding="utf-8",
    )


def _read_settings(project_dir: Path) -> dict:
    return json.loads((project_dir / ".claude" / "settings.json").read_text())


def _hook_entry_present(settings: dict) -> bool:
    """True iff our PostToolUse `validate-on-edit` entry is in the file."""
    pth = settings.get("hooks", {}).get("PostToolUse", [])
    for block in pth:
        for h in block.get("hooks", []):
            if "tripwire hook validate-on-edit" in h.get("command", ""):
                return True
    return False


def test_install_creates_settings_when_absent(tmp_path: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        cli, ["hooks", "install", "--project-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.is_file()
    settings = _read_settings(tmp_path)
    assert _hook_entry_present(settings)


def test_install_is_idempotent(tmp_path: Path) -> None:
    """Re-running install on a project where the hook is already present
    must produce no diff (no duplicate entry)."""
    _project(tmp_path)
    runner = CliRunner()

    runner.invoke(cli, ["hooks", "install", "--project-dir", str(tmp_path)])
    settings_path = tmp_path / ".claude" / "settings.json"
    first = settings_path.read_text()

    result = runner.invoke(
        cli, ["hooks", "install", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0

    second = settings_path.read_text()
    assert json.loads(first) == json.loads(second), (
        "second install should be a no-op (idempotent)"
    )


def test_install_merges_with_existing_unrelated_settings(tmp_path: Path) -> None:
    """Pre-existing user settings (e.g. theme, env) are preserved on merge."""
    _project(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    pre = {"env": {"FOO": "bar"}, "permissions": {"allow": ["Bash(ls:*)"]}}
    (claude_dir / "settings.json").write_text(json.dumps(pre))

    runner = CliRunner()
    result = runner.invoke(
        cli, ["hooks", "install", "--project-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    merged = _read_settings(tmp_path)
    assert merged["env"] == {"FOO": "bar"}, "must preserve unrelated keys"
    assert merged["permissions"] == {"allow": ["Bash(ls:*)"]}
    assert _hook_entry_present(merged)


def test_install_force_overwrites_existing_hooks_block(tmp_path: Path) -> None:
    """`--force` replaces the hooks block but preserves other keys."""
    _project(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    pre = {
        "env": {"FOO": "bar"},
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo legacy"}],
                }
            ]
        },
    }
    (claude_dir / "settings.json").write_text(json.dumps(pre))

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["hooks", "install", "--force", "--project-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    merged = _read_settings(tmp_path)
    assert merged["env"] == {"FOO": "bar"}
    # Force replaces the hooks block — legacy entry is gone, ours is in
    pth = merged["hooks"]["PostToolUse"]
    assert all("echo legacy" not in str(b) for b in pth)
    assert _hook_entry_present(merged)
