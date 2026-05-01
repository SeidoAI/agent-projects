"""``tripwire test-tripwire <id>`` — fire one tripwire against a fixture context.

Authoring tooling for project-team tripwire authors (KUI-136 / B2).
The command loads the project's tripwire registry, finds the named
tripwire, instantiates a synthetic :class:`TripwireContext`, and
prints the prompt that ``fire()`` would return. With ``--ack``, it
writes the standard substantive ack marker so the next run sees the
ack path resolved.

PM-only by the same role marker as ``tripwire tripwires`` — the
authoring loop is meant for the team designing process, not for
agents.
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project


def _is_pm() -> bool:
    """Mirror of ``cli/tripwires.py:_is_pm`` so we don't pull a circular import."""
    env_role = os.environ.get("TRIPWIRE_ROLE", "").strip().lower()
    if env_role == "pm":
        return True
    home = os.environ.get("TRIPWIRE_HOME") or os.path.expanduser("~/.tripwire")
    role_path = Path(home) / "role"
    if role_path.is_file():
        try:
            value = role_path.read_text(encoding="utf-8").strip().lower()
        except OSError:
            return False
        return value == "pm"
    return False


def _require_pm() -> None:
    if not _is_pm():
        raise click.ClickException(
            "`tripwire test-tripwire` is PM-only. Set `TRIPWIRE_ROLE=pm` "
            "or write `pm` to `~/.tripwire/role` (or `$TRIPWIRE_HOME/role`) "
            "and re-run."
        )


_DEFAULT_SESSION_ID = "_test"
"""Default session id for ``test-tripwire``. Underscored so it can't
collide with a real session id (real ids never start with ``_``) and
filesystem-safe on Windows (the ack-marker filename is
``<tripwire-id>-<session-id>.json`` — angle brackets are invalid on
NTFS)."""


@click.command("test-tripwire")
@click.argument("tripwire_id")
@click.option(
    "--session",
    "session_id",
    default=_DEFAULT_SESSION_ID,
    show_default=True,
    help="Session id used to seed the variation_index hash.",
)
@click.option(
    "--ack",
    "write_ack",
    is_flag=True,
    default=False,
    help="Write a substantive ack marker so subsequent fires don't block.",
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def test_tripwire_cmd(
    tripwire_id: str,
    session_id: str,
    write_ack: bool,
    project_dir: Path,
) -> None:
    """Fire ``TRIPWIRE_ID`` against a synthetic context and print the prompt.

    Useful for iterating on prompt copy without spawning a real
    session. With ``--ack`` the command also writes the substantive
    ack marker (``fix_commits=["<test>"]``) so the ack path is
    exercised end-to-end.
    """
    from tripwire._internal.tripwires import TripwireContext
    from tripwire._internal.tripwires.loader import load_registry
    from tripwire.core.store import load_project
    from tripwire.core.tripwire_state import write_ack_marker

    _require_pm()

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    registry = load_registry(resolved)
    by_id = {tw.id: (event, tw) for event, tws in registry.items() for tw in tws}
    if tripwire_id not in by_id:
        known = ", ".join(sorted(by_id.keys())) or "(empty)"
        raise click.ClickException(
            f"unknown tripwire id {tripwire_id!r}; known: {known}"
        )

    project = load_project(resolved)
    project_slug = project.name.lower().replace(" ", "-")
    ctx = TripwireContext(
        project_dir=resolved,
        session_id=session_id,
        project_id=project_slug,
    )

    _event, tripwire = by_id[tripwire_id]
    prompt = tripwire.fire(ctx)
    click.echo(prompt)

    if write_ack:
        marker = write_ack_marker(
            project_dir=resolved,
            session_id=session_id,
            tripwire_id=tripwire_id,
            fix_commits=["<test>"],
            declared_no_findings=False,
        )
        click.echo(f"Wrote ack marker: {marker}")
