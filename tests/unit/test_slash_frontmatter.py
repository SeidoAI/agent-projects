"""Every pm-*.md slash command file must have valid frontmatter.

Checks: filename matches frontmatter.name; description ≤ 80 chars;
argument-hint present for commands that take arguments; every command
is in the v0.6a allowlist (catches accidental adds or drops).
"""

from pathlib import Path

import yaml

COMMANDS_DIR = (
    Path(__file__).parent.parent.parent / "src" / "tripwire" / "templates" / "commands"
)

ALLOWED_NAMES = {
    # Entity-scoped
    "pm-issue-close",
    "pm-issue-artifact",  # v0.7b — per-issue artifacts
    "pm-session-create",
    "pm-session-queue",
    "pm-session-spawn",  # v0.6c
    "pm-session-check",
    "pm-session-progress",
    "pm-session-agenda",  # v0.6c
    "pm-session-monitor",  # v0.7b
    "pm-session-review",  # v0.7b
    "pm-session-complete",  # v0.7b
    "pm-project-create",  # v0.6b
    "pm-project-sync",  # v0.6b
    # Non-entity verbs
    "pm-scope",
    "pm-rescope",
    "pm-triage",
    "pm-edit",
    "pm-review",
    "pm-validate",
    "pm-lint",
    # Interpretive
    "pm-status",
    "pm-agenda",
    "pm-graph",
    # Deprecated forwarders (still shipped in v0.6a — removed in v0.7)
    "pm-handoff",
    "pm-close",
    "pm-update",
    "pm-plan",
}

# Commands that take arguments must have an argument-hint.
COMMANDS_THAT_TAKE_ARGS = ALLOWED_NAMES - {
    "pm-status",
    "pm-agenda",
    "pm-session-agenda",
    "pm-graph",
    "pm-triage",
    "pm-validate",
    "pm-project-sync",  # v0.6b — no required args
}


def _load_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name} missing frontmatter start delimiter"
    parts = text.split("---", 2)
    return yaml.safe_load(parts[1])


def test_every_file_has_name_matching_filename():
    for path in COMMANDS_DIR.glob("pm-*.md"):
        fm = _load_frontmatter(path)
        assert fm["name"] == path.stem, (
            f"{path.name}: frontmatter name {fm['name']!r} != filename stem {path.stem!r}"
        )


def test_every_file_has_description():
    for path in COMMANDS_DIR.glob("pm-*.md"):
        fm = _load_frontmatter(path)
        assert fm.get("description"), f"{path.name}: missing or empty description"
        assert len(fm["description"]) <= 80, (
            f"{path.name}: description > 80 chars: {fm['description']!r}"
        )


def test_every_command_is_in_allowlist():
    actual = {p.stem for p in COMMANDS_DIR.glob("pm-*.md")}
    unknown = actual - ALLOWED_NAMES
    assert not unknown, f"unknown commands not in v0.6a allowlist: {unknown}"
    # v0.6a doesn't ship pm-project-* (v0.6b) or pm-issue-artifact (v0.7b).
    expected_on_disk = ALLOWED_NAMES - {
        "pm-project-create",
        "pm-project-sync",
    }
    missing = expected_on_disk - actual
    assert not missing, f"expected commands missing from disk: {missing}"


def test_argument_hint_present_when_command_takes_args():
    for name in COMMANDS_THAT_TAKE_ARGS:
        path = COMMANDS_DIR / f"{name}.md"
        if not path.exists():
            continue  # v0.6b commands skipped in v0.6a
        fm = _load_frontmatter(path)
        assert "argument-hint" in fm, f"{name}: missing argument-hint"
