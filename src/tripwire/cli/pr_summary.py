"""``tripwire pr-summary`` — render a PR comment for a base..head diff.

Designed to run from CI (see the workflow template in
``templates/project/.github/workflows/pr-summary.yml.j2``): the action
checks out the PR branch with ``fetch-depth: 0`` so both base and head
SHAs are resolvable, then pipes this command's stdout into
``peter-evans/create-or-update-comment``.

The first line of stdout is the discriminator marker
``<!-- tripwire-pr-summary -->``; the action's ``body-includes`` config
matches on it so re-runs update the same comment instead of stacking new
ones.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import click

from tripwire.core.pr_summary_compute import compute_pr_summary
from tripwire.core.pr_summary_renderer import render


@click.command(name="pr-summary")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Path to the project root (contains project.yaml).",
)
@click.option(
    "--base",
    "base_sha",
    default="origin/main",
    show_default=True,
    help="Base ref to diff against. Any form git rev-parse accepts.",
)
@click.option(
    "--head",
    "head_sha",
    default="HEAD",
    show_default=True,
    help="Head ref. Any form git rev-parse accepts.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    show_default=True,
    help="Markdown comment body, or structured JSON for downstream tooling.",
)
def pr_summary_cmd(
    project_dir: Path,
    base_sha: str,
    head_sha: str,
    output_format: str,
) -> None:
    """Render the PR-summary comment for the given base..head diff."""
    project_resolved = project_dir.expanduser().resolve()
    repo_root = _git_toplevel(project_resolved)
    rel_project = project_resolved.relative_to(repo_root)

    summary = compute_pr_summary(
        repo_root,
        base_sha=base_sha,
        head_sha=head_sha,
        project_dir=str(rel_project) if str(rel_project) != "." else "",
    )

    if output_format == "json":
        click.echo(json.dumps(asdict(summary), indent=2, default=str))
    else:
        click.echo(render(summary), nl=False)


def _git_toplevel(start: Path) -> Path:
    """Resolve the root of the git repo containing *start*."""
    try:
        result = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(
            f"{start} is not inside a git repository (git rev-parse failed)."
        ) from exc
    return Path(result.stdout.strip())
