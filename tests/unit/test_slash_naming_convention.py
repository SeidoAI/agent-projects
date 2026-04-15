"""Entity-scoped pm-<entity>-<verb> commands use an allowed entity.

Non-entity commands (pm-scope, pm-triage, pm-validate, etc.) have
only 2 hyphens in their stem and skip the check. Interpretive
commands (pm-status, pm-agenda, pm-graph) also have 2 hyphens.
"""

from pathlib import Path

COMMANDS_DIR = (
    Path(__file__).parent.parent.parent
    / "src"
    / "keel"
    / "templates"
    / "commands"
)

ALLOWED_ENTITIES = {"issue", "session", "project", "workspace"}


def test_entity_prefixed_commands_use_allowed_entity():
    for path in COMMANDS_DIR.glob("pm-*.md"):
        stem = path.stem  # e.g., pm-session-launch
        parts = stem.split("-")
        # 2-part stems (pm-scope, pm-edit, pm-status) skip the check.
        if len(parts) < 3:
            continue
        entity = parts[1]
        assert entity in ALLOWED_ENTITIES, (
            f"{stem}: entity {entity!r} not in allowed set {ALLOWED_ENTITIES}"
        )
