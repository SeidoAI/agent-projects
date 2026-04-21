"""Tests for the packaged `/pm-*` slash command templates.

These templates ship at `src/tripwire/templates/commands/` and are copied
into `.claude/commands/` in every initialized project. Each is a
Markdown file with a YAML frontmatter block containing at minimum a
`name`, `description`, and `argument-hint`.

Tests verify:
- Every expected file exists
- Frontmatter is valid YAML and contains the required fields
- The `name` field matches the filename stem
- No command references the old `agent-project` CLI name or
  `scaffold-for-creation`
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tripwire.templates import get_templates_dir

COMMANDS_DIR = get_templates_dir() / "commands"

EXPECTED_COMMANDS: tuple[str, ...] = (
    # v0.6a retained + renamed + new commands:
    "pm-agenda",
    "pm-edit",
    "pm-graph",
    "pm-issue-close",
    "pm-lint",
    "pm-rescope",
    "pm-review",
    "pm-scope",
    "pm-session-agenda",
    "pm-session-check",
    "pm-session-create",
    "pm-session-queue",
    "pm-session-progress",
    "pm-session-spawn",
    "pm-status",
    "pm-triage",
    "pm-validate",
    # v0.6b workspace commands:
    "pm-project-create",
    "pm-project-sync",
    # v0.7b per-issue artifact command:
    "pm-issue-artifact",
    # v0.7b session monitor:
    "pm-session-monitor",
    # v0.7b session review:
    "pm-session-review",
    # v0.7b session complete:
    "pm-session-complete",
    # Deprecated forwarders (still shipped, removed in v0.7):
    "pm-close",
    "pm-handoff",
    "pm-plan",
    "pm-update",
)

REQUIRED_FRONTMATTER_FIELDS: tuple[str, ...] = ("name", "description", "argument-hint")


def _parse_frontmatter(path: Path) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from a .md file.

    Returns (frontmatter_dict, body_str). Raises ValueError if the file
    does not begin with a `---` frontmatter block.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: missing leading `---` frontmatter delimiter")
    # Find the closing `---` after the opening one
    rest = text[4:]
    end = rest.find("\n---\n")
    if end == -1:
        raise ValueError(f"{path.name}: missing closing `---` frontmatter delimiter")
    frontmatter_text = rest[:end]
    body = rest[end + 5 :]
    frontmatter = yaml.safe_load(frontmatter_text)
    if not isinstance(frontmatter, dict):
        raise ValueError(f"{path.name}: frontmatter is not a YAML mapping")
    return frontmatter, body


def test_commands_directory_exists() -> None:
    assert COMMANDS_DIR.is_dir(), f"Missing directory: {COMMANDS_DIR}"


@pytest.mark.parametrize("command_name", EXPECTED_COMMANDS)
def test_command_file_exists(command_name: str) -> None:
    path = COMMANDS_DIR / f"{command_name}.md"
    assert path.is_file(), f"Missing command file: {path}"


def test_expected_commands_present() -> None:
    found = sorted(p.stem for p in COMMANDS_DIR.glob("*.md"))
    assert sorted(EXPECTED_COMMANDS) == found, (
        f"Expected exactly {len(EXPECTED_COMMANDS)} command files, got {len(found)}"
    )


@pytest.mark.parametrize("command_name", EXPECTED_COMMANDS)
def test_command_has_valid_frontmatter(command_name: str) -> None:
    path = COMMANDS_DIR / f"{command_name}.md"
    frontmatter, _ = _parse_frontmatter(path)
    for field in REQUIRED_FRONTMATTER_FIELDS:
        assert field in frontmatter, f"{command_name}: missing `{field}` in frontmatter"


@pytest.mark.parametrize("command_name", EXPECTED_COMMANDS)
def test_command_name_matches_filename(command_name: str) -> None:
    path = COMMANDS_DIR / f"{command_name}.md"
    frontmatter, _ = _parse_frontmatter(path)
    assert frontmatter["name"] == command_name, (
        f"{command_name}.md has name={frontmatter['name']!r}, expected {command_name!r}"
    )


@pytest.mark.parametrize("command_name", EXPECTED_COMMANDS)
def test_command_body_references_keel_not_agent_project(command_name: str) -> None:
    """Every command body must use `tripwire <cmd>`, not `agent-project <cmd>`."""
    path = COMMANDS_DIR / f"{command_name}.md"
    _, body = _parse_frontmatter(path)
    assert "agent-project" not in body, (
        f"{command_name}: body references old `agent-project` name"
    )
    assert "scaffold-for-creation" not in body, (
        f"{command_name}: body references old `scaffold-for-creation` name"
    )


@pytest.mark.parametrize("command_name", EXPECTED_COMMANDS)
def test_command_body_uses_arguments_substitution(command_name: str) -> None:
    """Every command body should reference $ARGUMENTS so user input is used."""
    path = COMMANDS_DIR / f"{command_name}.md"
    _, body = _parse_frontmatter(path)
    assert "$ARGUMENTS" in body, (
        f"{command_name}: body does not reference $ARGUMENTS — user input will be ignored"
    )
