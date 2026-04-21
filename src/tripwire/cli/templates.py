"""`tripwire templates list|show` — explore the project's templates.

Read-only helper for exploring the template tree the project owns. The
source of truth is whatever files live under the template directories
in the project repo — the package's default templates are never read
here.

`templates list` walks the known template subdirectories and prints the
relative path of every file. `templates show <name>` tries to resolve
`<name>` to a file and print its contents.
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from tripwire.cli._utils import require_project as _require_project
from tripwire.core import paths

console = Console()

# Directories in a project repo that hold project-owned templates.
# `templates/artifacts` is the one exception that stays under `templates/`;
# everything else lives at the project root.
TEMPLATE_SUBDIRS = (
    paths.ISSUE_TEMPLATES_DIR,
    paths.COMMENT_TEMPLATES_DIR,
    paths.SESSION_TEMPLATES_DIR,
    paths.TEMPLATES_ARTIFACTS_DIR,
    paths.AGENTS_DIR,
    paths.ORCHESTRATION_DIR,
)


@click.group(name="templates")
def templates_cmd() -> None:
    """Explore the templates the project ships (read-only)."""


@templates_cmd.command("list")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def templates_list(project_dir: Path) -> None:
    """List every template file in the project."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    rows = _collect_templates(resolved)
    if not rows:
        console.print(
            "[dim]no templates in this project yet — Steps 9+ add the defaults[/dim]"
        )
        return

    table = Table(title="Project templates", show_header=True)
    table.add_column("path")
    table.add_column("kind")
    for path, kind in rows:
        table.add_row(path, kind)
    console.print(table)


@templates_cmd.command("show")
@click.argument("name")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def templates_show(name: str, project_dir: Path) -> None:
    """Print the contents of a template.

    NAME can be any relative path under a template subdirectory, or a bare
    filename that the command will search for across all template
    subdirectories.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    # Try the literal relative path first, then search.
    candidate = resolved / name
    if candidate.is_file():
        click.echo(candidate.read_text(encoding="utf-8"), nl=False)
        return

    matches = [
        (path, kind)
        for path, kind in _collect_templates(resolved)
        if path.endswith(name) or _template_base_name(path) == name
    ]
    if not matches:
        raise click.ClickException(
            f"No template matching {name!r} found in the project. "
            f"Run `tripwire templates list` to see what's available."
        )
    if len(matches) > 1:
        options = ", ".join(p for p, _ in matches)
        raise click.ClickException(
            f"Name {name!r} is ambiguous: {options}. Pass the full relative path."
        )
    click.echo((resolved / matches[0][0]).read_text(encoding="utf-8"), nl=False)


def _template_base_name(path: str) -> str:
    """Extract the logical template name from a file path.

    Handles double extensions like `default.yaml.j2` → `default`.
    Strips a trailing `.j2` first, then takes the stem. So:
      - `issue_templates/default.yaml.j2` → `default`
      - `agents/backend-coder.yaml` → `backend-coder`
      - `orchestration/default.yaml` → `default`
    """
    p = Path(path)
    if p.suffix == ".j2":
        p = p.with_suffix("")
    return p.stem


# ============================================================================
# Helpers
# ============================================================================


def _collect_templates(project_dir: Path) -> list[tuple[str, str]]:
    """Return [(relative_path, kind), ...] for every template file.

    `kind` is the subdirectory name — a crude categorisation the `list`
    output uses so users can see at a glance what each template is for.
    """
    rows: list[tuple[str, str]] = []
    for subdir in TEMPLATE_SUBDIRS:
        abs_dir = project_dir / subdir
        if not abs_dir.is_dir():
            continue
        for f in sorted(abs_dir.rglob("*")):
            if f.is_file() and f.name != ".gitkeep":
                rows.append((str(f.relative_to(project_dir)), subdir))
    return rows
