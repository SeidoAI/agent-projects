"""Prompt-check station mapping (KUI-122).

A prompt-check is a slash command (``pm-session-review``,
``pm-session-launch``, etc.) that the project manager runs at a
specific workflow station. The frontmatter on the slash command file
declares the station via ``fires_at:``:

.. code-block:: yaml

    ---
    name: pm-session-review
    fires_at: in_review
    description: ...
    ---

This module enumerates every slash command file (packaged defaults
under ``templates/commands/``, project-local overrides under
``.tripwire/commands/``), parses the frontmatter, and exposes the
``fires_at: → command-name`` mapping. The well-formedness validator
uses this to resolve workflow.yaml's ``prompt_checks: [...]`` refs.

Step 1 ships the surface; step 4 (KUI-122) backfills frontmatter on
the existing slash commands and starts emitting findings for
unresolved refs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PromptCheck:
    """A slash command that declares ``fires_at: <station-id>``."""

    id: str  # the command name (matches the frontmatter `name:`)
    fires_at: str
    source: Path  # absolute path to the .md file


def _packaged_commands_dir() -> Path:
    """Return the absolute path to the packaged ``templates/commands/`` dir."""
    import tripwire

    return Path(tripwire.__file__).parent / "templates" / "commands"


def collect_prompt_checks(project_dir: Path) -> list[PromptCheck]:
    """Enumerate every slash command that declares ``fires_at:``.

    Resolution: project-local override (``.tripwire/commands/<name>.md``)
    wins over the packaged default. Files without frontmatter, or
    without a ``fires_at:`` key, are skipped — they're slash commands
    that aren't workflow prompt-checks.
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

    Returns ``None`` if the file has no frontmatter, no ``fires_at:``,
    or any parse failure — these aren't errors at this layer; they're
    "this slash command isn't a prompt-check".
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    fm_text = text[4:end]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    fires_at = fm.get("fires_at")
    name = fm.get("name") or path.stem
    if not isinstance(fires_at, str) or not fires_at:
        return None
    return PromptCheck(id=str(name), fires_at=fires_at, source=path)


__all__ = ["PromptCheck", "collect_prompt_checks"]
