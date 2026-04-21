"""`tripwire ci` — install the project-side CI workflow.

Renders `templates/project/.github/workflows/tripwire.yml.j2` into the
project's `.github/workflows/tripwire.yml`, pinned to the project's
`tripwire_version` (or the currently-installed tripwire as a fallback).
"""

from __future__ import annotations

from pathlib import Path

import click
from jinja2 import Environment, FileSystemLoader

from tripwire import __version__ as _installed_tripwire_version
from tripwire.cli._utils import require_project as _require_project
from tripwire.core.store import load_project


@click.group(name="ci")
def ci_cmd() -> None:
    """Project CI workflow management."""


@ci_cmd.command("install")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite an existing .github/workflows/tripwire.yml.",
)
@click.option(
    "--version",
    "version_override",
    default=None,
    help="Pin to this tripwire version (defaults to project.tripwire_version "
    "or the installed CLI's version).",
)
def ci_install_cmd(
    project_dir: Path, force: bool, version_override: str | None
) -> None:
    """Render the tripwire CI workflow into the project."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    project = load_project(resolved)
    version = (
        version_override or project.tripwire_version or _installed_tripwire_version
    )

    target = resolved / ".github" / "workflows" / "tripwire.yml"
    if target.is_file() and not force:
        raise click.ClickException(
            f"{target} already exists. Use --force to overwrite."
        )

    import tripwire as _tripwire

    template_root = (
        Path(_tripwire.__file__).parent
        / "templates"
        / "project"
        / ".github"
        / "workflows"
    )
    env = Environment(
        loader=FileSystemLoader(str(template_root)),
        keep_trailing_newline=True,
    )
    template = env.get_template("tripwire.yml.j2")
    rendered = template.render(tripwire_version=version)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    click.echo(f"Wrote {target.relative_to(resolved)} (pinned to {version})")
