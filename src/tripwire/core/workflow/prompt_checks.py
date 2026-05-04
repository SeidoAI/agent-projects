"""Prompt-check implementation catalog (KUI-122).

A prompt-check is a slash command (``pm-session-review``,
``pm-session-launch``, etc.) that the project manager runs at a
workflow status declared by ``workflow.yaml``. Slash command files
provide the implementation id and optional description:

.. code-block:: yaml

    ---
    name: pm-session-review
    description: ...
    ---

This module enumerates every slash command file (packaged defaults
under ``templates/commands/``, project-local overrides under
``.tripwire/commands/``), parses the frontmatter, and exposes command
ids. The well-formedness validator uses this to resolve
workflow.yaml's ``prompt_checks: [...]`` refs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

LIFECYCLE_PROMPT_CHECK_IDS = frozenset(
    {
        "pm-session-create",
        "pm-session-queue",
        "pm-session-spawn",
        "pm-session-review",
        "pm-session-complete",
    }
)


@dataclass(frozen=True)
class PromptCheck:
    """A slash command that can be referenced by ``workflow.yaml``."""

    id: str  # the command name (matches the frontmatter `name:`)
    description: str
    source: Path  # absolute path to the .md file


def _packaged_commands_dir() -> Path:
    """Return the absolute path to the packaged ``templates/commands/`` dir."""
    import tripwire

    return Path(tripwire.__file__).parent / "templates" / "commands"


def collect_prompt_checks(project_dir: Path) -> list[PromptCheck]:
    """Enumerate slash commands that can be workflow prompt-checks.

    Resolution: project-local override (``.tripwire/commands/<name>.md``)
    wins over the packaged default.
    """
    seen: dict[str, PromptCheck] = {}
    # Packaged defaults first; overrides applied after to win.
    for source_dir in (
        _packaged_commands_dir(),
        project_dir / ".tripwire" / "commands",
    ):
        if not source_dir.is_dir():
            continue
        for md in sorted(source_dir.glob("*.md")):
            entry = _parse_command_file(md)
            if entry is None:
                continue
            seen[entry.id] = entry
    return list(seen.values())


def _parse_command_file(path: Path) -> PromptCheck | None:
    """Parse a single ``.md`` frontmatter and return a :class:`PromptCheck`.

    Returns ``None`` only when the file cannot be read or parsed. The
    command name falls back to the file stem so workflow.yaml can
    reference older commands that have no frontmatter.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---\n"):
        return PromptCheck(id=path.stem, description="", source=path)
    end = text.find("\n---", 4)
    if end == -1:
        return PromptCheck(id=path.stem, description="", source=path)
    fm_text = text[4:end]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return PromptCheck(id=path.stem, description="", source=path)
    if not isinstance(fm, dict):
        return PromptCheck(id=path.stem, description="", source=path)
    name = fm.get("name") or path.stem
    description = fm.get("description")
    return PromptCheck(
        id=str(name),
        description=str(description) if isinstance(description, str) else "",
        source=path,
    )


__all__ = ["LIFECYCLE_PROMPT_CHECK_IDS", "PromptCheck", "collect_prompt_checks"]
