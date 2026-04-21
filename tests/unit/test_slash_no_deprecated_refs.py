"""Slash command bodies must not reference removed commands or CLI verbs.

Deprecated forwarders are allowed to mention new command names (they
point users at them). Regular (non-forwarder) commands must not use
the old names anywhere in their prose.
"""

from pathlib import Path

COMMANDS_DIR = (
    Path(__file__).parent.parent.parent / "src" / "tripwire" / "templates" / "commands"
)

FORWARDER_FILES = {"pm-handoff.md", "pm-close.md", "pm-update.md", "pm-plan.md"}

# Regular commands should not reference these removed verbs.
FORBIDDEN_IN_REGULAR = {
    "tripwire workspace new-project",  # replaced by tripwire init --workspace (v0.6b)
    "/pm-handoff",
    "/pm-close",
    "/pm-update",
    "/pm-plan",
}


def test_no_regular_command_references_deprecated():
    for path in COMMANDS_DIR.glob("pm-*.md"):
        if path.name in FORWARDER_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_IN_REGULAR:
            assert forbidden not in text, (
                f"{path.name}: references deprecated token {forbidden!r}"
            )


def test_forwarders_mention_replacement():
    """Every forwarder file must mention the command it forwards to."""
    replacements = {
        "pm-handoff.md": ("pm-session-create", "pm-session-launch"),
        "pm-close.md": ("pm-issue-close",),
        "pm-update.md": ("pm-edit",),
        "pm-plan.md": ("tripwire plan",),
    }
    for name, expected in replacements.items():
        path = COMMANDS_DIR / name
        text = path.read_text(encoding="utf-8")
        for token in expected:
            assert token in text, (
                f"{name}: forwarder must mention replacement {token!r}"
            )
