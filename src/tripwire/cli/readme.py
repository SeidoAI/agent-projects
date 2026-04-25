"""`tripwire readme generate` — write or check the auto-generated README.

The CD workflow runs this on every push to main; humans run it via
pre-commit (`--check`) or to refresh the README locally. The renderer
itself lives in `tripwire.core.readme_renderer`; this module is just
the Click adapter + the optional `gh pr list` enrichment for the
"Recent merges" section.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import click

from tripwire.cli._utils import require_project
from tripwire.core.readme_renderer import render

# Default to fetching this many merged PRs for the "Recent merges" section.
# Five is enough for one screenful and keeps the gh request small.
DEFAULT_MERGES_LIMIT = 5


@click.group(name="readme")
def readme_cmd() -> None:
    """Generate or check the project README."""


@readme_cmd.command("generate")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Path to the project root (contains project.yaml).",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the rendered README here. Defaults to <project-dir>/README.md.",
)
@click.option(
    "--template",
    "template_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help=(
        "Override the default template. Resolves explicit arg → "
        "<project>/.tripwire/readme.md.j2 → packaged default."
    ),
)
@click.option(
    "--check",
    is_flag=True,
    help=(
        "Exit 1 if the rendered output differs from the file at --output, "
        "0 if identical. For pre-commit / non-CD use."
    ),
)
@click.option(
    "--merges-limit",
    type=int,
    default=DEFAULT_MERGES_LIMIT,
    show_default=True,
    help=(
        "Number of recent merged PRs to include via `gh pr list`. Set to 0 "
        "to skip. Silently skipped if `gh` is not on PATH or fails."
    ),
)
def readme_generate_cmd(
    project_dir: Path,
    output_path: Path | None,
    template_path: Path | None,
    check: bool,
    merges_limit: int,
) -> None:
    """Render the project's README from its current state."""
    resolved_dir = project_dir.expanduser().resolve()
    require_project(resolved_dir)

    output = output_path or (resolved_dir / "README.md")
    output = output.expanduser().resolve()

    recent_merges = _fetch_recent_merges(resolved_dir, merges_limit)

    rendered = render(
        resolved_dir,
        template_path=template_path,
        recent_merges=recent_merges,
    )

    if check:
        existing = output.read_text(encoding="utf-8") if output.is_file() else ""
        if existing == rendered:
            click.echo(f"README in sync: {output}")
            return
        click.echo(f"README out of sync: {output}", err=True)
        click.echo("Run `tripwire readme generate` to update.", err=True)
        sys.exit(1)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    click.echo(f"Wrote {output}")


def _fetch_recent_merges(project_dir: Path, limit: int) -> list[str] | None:
    """Best-effort fetch of recent merged PRs via `gh pr list`.

    Returns:
        A list of one-line summaries, or None if `gh` is unavailable or
        the call failed. None means "leave the section empty"; an empty
        list means "explicitly no merges to show".
    """
    if limit <= 0:
        return None
    if shutil.which("gh") is None:
        return None
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "merged",
                "--limit",
                str(limit),
                "--json",
                "number,title,mergedAt",
            ],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    return [
        f"#{item.get('number', '?')} {item.get('title', '').strip()}" for item in items
    ]
