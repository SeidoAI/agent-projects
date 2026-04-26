"""Module hygiene tests for the ``_internal/tripwires`` package.

The tripwire primitive's effectiveness depends on the executing
agent NOT being able to read the prompts before they fire. We
enforce this with three checks:

1. ``tripwire/__init__.py`` does NOT re-export anything from
   ``_internal/`` (so ``from tripwire import ...`` can't reach it).
2. The skill loader (``runtimes/prep.py.copy_skills``) does not pull
   anything from ``_internal/`` into ``.claude/skills/``.
3. No template, doc, or spec under ``src/tripwire/templates`` mentions
   ``_internal/tripwires/`` or names a registered tripwire's prompt.

These are not security boundaries — an agent that greps the source
will find prompts. They are the "do not load by default" defence the
spec calls for in §5 + §7.
"""

from __future__ import annotations

import re
from pathlib import Path

import tripwire

_TRIPWIRE_SRC = Path(tripwire.__file__).parent
_INTERNAL_TRIPWIRES = _TRIPWIRE_SRC / "_internal" / "tripwires"
_TEMPLATES = _TRIPWIRE_SRC / "templates"


def test_public_init_does_not_re_export_internal() -> None:
    """``tripwire/__init__.py`` source must not import or export anything
    from ``_internal/``.

    Note: ``tripwire._internal`` may still appear in ``dir(tripwire)``
    once another module has imported it (Python caches submodules on
    the parent). The contract is about authored re-exports, not the
    transitive submodule cache. We sentinel on the source file
    directly so the check is robust to import order.
    """
    init_src = (Path(tripwire.__file__)).read_text(encoding="utf-8")
    assert "_internal" not in init_src, (
        "tripwire/__init__.py references _internal — agents that "
        "`from tripwire import ...` would reach tripwire prompts."
    )
    for name in ("Tripwire", "TripwireContext", "fire_event"):
        assert name not in init_src, (
            f"{name!r} appears in tripwire/__init__.py — that re-exports "
            f"a tripwire surface to the public namespace."
        )


def test_internal_tripwires_directory_exists() -> None:
    assert _INTERNAL_TRIPWIRES.is_dir(), _INTERNAL_TRIPWIRES


def test_no_template_references_internal_tripwires() -> None:
    """Agent-visible templates must not name the internal tripwires path."""
    needle = "_internal/tripwires"
    offenders: list[Path] = []
    for path in _TEMPLATES.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if needle in text:
            offenders.append(path.relative_to(_TRIPWIRE_SRC))
    assert offenders == [], (
        f"Templates leak the internal tripwires path: {offenders}. "
        f"Move references out so the executing agent's read-path doesn't "
        f"pull tripwire prompt content."
    )


def test_skill_loader_skips_internal() -> None:
    """``copy_skills`` reads from ``templates/skills/`` only — never
    from ``_internal/``. Verify by inspecting the source: the function
    must construct its source root from the templates path, not from a
    location that could resolve into ``_internal/``."""
    from tripwire.runtimes import prep

    prep_src = Path(prep.__file__).read_text(encoding="utf-8")
    # The function must scope itself to templates/skills.
    assert "templates" in prep_src and "skills" in prep_src
    # And must not reach into _internal.
    assert not re.search(r"_internal[\\/]tripwires", prep_src), (
        "runtimes/prep.py references _internal/tripwires — that's the leak."
    )
