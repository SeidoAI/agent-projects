"""`tripwire init` — create a new project from the packaged templates.

The command is interactive by default: any required option that wasn't
passed as a flag gets a prompt. Use `--non-interactive` to fail fast if any
required flag is missing (for scripts and CI).

What init does, in order:
1. Resolve the target path (argument or current directory)
2. Collect all required config: name, key_prefix, base_branch, repos
3. Refuse to overwrite an existing `project.yaml` unless `--force`
4. Copy the entire `templates/` tree from the package into the target
5. Render `.j2` files through Jinja2 with the collected config
6. Create the empty subdirectories the project expects (`issues/`,
   `nodes/`, `sessions/`, `plans/`) with `.gitkeep`
7. Run `git init` (unless `--no-git`) and stage the initial tree

After init, the project owns the copied templates and is ready for the
agent to start scoping from raw planning docs.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel

from tripwire.templates import get_templates_dir

KEY_PREFIX_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*$")

# Constants describing the template-tree layout (CREATED_DIRS,
# JINJA_RENDERED_SUBDIRS, VERBATIM_TEMPLATE_MAPPINGS, ROOT_J2_FILES)
# now live in core/init_templates.py — there's only one consumer here
# (the `_copy_templates` wrapper) so we don't re-export them.

console = Console()


class InitError(click.ClickException):
    """Raised when init cannot proceed (e.g. missing args, existing project)."""


# ============================================================================
# Input collection (interactive + flags)
# ============================================================================


def _prompt_for_name(default: str | None) -> str:
    name = click.prompt("Project name", default=default, type=str)
    if not name.strip():
        raise InitError("Project name cannot be empty.")
    return name.strip()


def _prompt_for_key_prefix(default: str | None = None) -> str:
    """Prompt for a key prefix, optionally with an auto-extracted default.

    If `default` is provided (and passes validation) it's shown as the prompt
    default — the user can hit Enter to accept it or type a different value.
    """
    prompt_label = "Issue key prefix"
    if default is not None:
        prompt_label = "Issue key prefix (extracted from name)"
    while True:
        prefix = click.prompt(
            prompt_label,
            default=default,
            type=str,
            show_default=default is not None,
        )
        prefix = prefix.strip().upper()
        if KEY_PREFIX_PATTERN.match(prefix):
            return prefix
        click.echo(
            "  Invalid prefix. Must start with an uppercase letter and contain "
            "only uppercase letters and digits (e.g. SEI, PKB, X1)."
        )


def _prompt_for_base_branch(default: str) -> str:
    return click.prompt("Default base branch", default=default, type=str).strip()


def _prompt_for_repos() -> list[str]:
    raw = click.prompt(
        "Target GitHub repos (comma-separated slugs, blank to skip)",
        default="",
        show_default=False,
        type=str,
    )
    return _parse_repos(raw)


def _parse_repos(raw: str) -> list[str]:
    """Parse a comma-separated list of GitHub slugs, trimming whitespace."""
    if not raw:
        return []
    return [r.strip() for r in raw.split(",") if r.strip()]


def _guess_local_for_slug(slug: str, cwd: Path) -> str | None:
    """Look for a sibling directory whose basename matches the repo name.

    `cwd` is where `tripwire init` is running; typically projects sit in
    a monorepo-ish parent where the clone lives a directory or two
    over. Check the parent and grandparent for a directory whose name
    matches ``slug.split('/')[-1]`` — an exact basename match is a
    high-signal guess and almost never wrong.
    """
    repo_name = slug.split("/")[-1]
    for parent in (cwd.parent, cwd.parent.parent):
        candidate = parent / repo_name
        if candidate.is_dir() and (candidate / ".git").exists():
            return str(candidate)
    return None


def _prompt_for_repo_locals(slugs: list[str], cwd: Path) -> dict[str, str | None]:
    """For each repo slug, prompt for the local clone path.

    Without `local`, `tripwire session spawn` can't find the clone and
    fails with "No local clone for X. Set local path in project.yaml
    repos." (see `runtimes/prep.py`). Prompting up-front saves the
    round-trip.

    The prompt defaults to a sibling directory whose basename matches
    the repo name if such a clone exists on disk; otherwise the user
    types a path (or leaves blank to skip — we record null and they
    can fix it later).
    """
    locals_map: dict[str, str | None] = {}
    for slug in slugs:
        guess = _guess_local_for_slug(slug, cwd)
        answer = click.prompt(
            f"  Local clone path for {slug} (blank to skip)",
            default=guess or "",
            show_default=bool(guess),
            type=str,
        ).strip()
        locals_map[slug] = answer or None
    return locals_map


def _validate_key_prefix(prefix: str) -> str:
    prefix = prefix.strip().upper()
    if not KEY_PREFIX_PATTERN.match(prefix):
        raise InitError(
            f"Invalid key prefix {prefix!r}: must start with an uppercase "
            f"letter and contain only uppercase letters and digits."
        )
    return prefix


# Characters that separate word segments in a project name. camelCase
# and PascalCase boundaries are handled separately by the regex below.
_SEGMENT_SPLIT_PATTERN = re.compile(r"[-_\s\.]+")

# Matches camelCase / PascalCase boundaries — insert a split before any
# uppercase letter that follows a lowercase letter or digit.
_CAMEL_BOUNDARY_PATTERN = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _extract_key_prefix(name: str) -> str | None:
    """Auto-extract a key prefix from a project name.

    Splits the name on hyphens, underscores, spaces, and dots, AND on
    camelCase / PascalCase boundaries. Takes the first letter of each
    segment and uppercases. If the result is a single character, pads
    with the second letter of the first segment (so `backend` → `BA`
    rather than `B`). Returns `None` if extraction cannot produce a
    prefix matching `KEY_PREFIX_PATTERN` (e.g. the name starts with a
    digit, or contains only non-alphabetic characters).

    Examples:
        `my-project-cool` → `MPC`
        `my_project_cool` → `MPC`
        `MyProjectCool` → `MPC`
        `my project cool` → `MPC`
        `backend` → `BA` (padded)
        `agent-project` → `AP`
        `2024-retro` → `None` (leading digit → invalid)
        `` → `None`
    """
    if not name:
        return None

    # First pass: split on separators.
    segments = [s for s in _SEGMENT_SPLIT_PATTERN.split(name) if s]
    if not segments:
        return None

    # Second pass: split each segment on camelCase boundaries so
    # `MyProjectCool` → `[My, Project, Cool]` before letter extraction.
    expanded: list[str] = []
    for seg in segments:
        expanded.extend(s for s in _CAMEL_BOUNDARY_PATTERN.split(seg) if s)
    if not expanded:
        return None

    # Take the first alphanumeric character of each segment. Segments
    # that start with a digit are allowed in the middle but not in the
    # lead position (KEY_PREFIX_PATTERN requires a leading letter).
    initials = [seg[0].upper() for seg in expanded if seg[0].isalnum()]
    if not initials:
        return None

    prefix = "".join(initials)

    # Pad single-character prefixes from the second letter of the
    # first segment (e.g. `backend` → `BA`, not just `B`).
    if len(prefix) == 1 and len(expanded[0]) >= 2:
        second_char = expanded[0][1]
        if second_char.isalnum():
            prefix = prefix + second_char.upper()

    # Validate against the final regex. If the extraction produced
    # something invalid (e.g. leading digit), return None and let the
    # caller fall back to prompting.
    if not KEY_PREFIX_PATTERN.match(prefix):
        return None
    return prefix


# Template-tree copy + Jinja rendering live in core/init_templates.py.
# Aliased under the underscore names that init_cmd already calls.
from tripwire.core.init_templates import (
    copy_templates as _copy_templates_core,
)
from tripwire.core.init_templates import (
    create_project_dirs as _create_project_dirs,
)


def _copy_templates(
    templates_dir: Path, target_dir: Path, context: dict[str, Any]
) -> list[Path]:
    """CLI wrapper — see :func:`tripwire.core.init_templates.copy_templates`."""
    try:
        return _copy_templates_core(templates_dir, target_dir, context)
    except ValueError as exc:
        raise InitError(str(exc)) from exc


# ============================================================================
# Git init
# ============================================================================


# Git + GitHub remote setup (v0.7.6 §2.A) lives in core/init_github.py.
# Import the public-named versions and alias them under the underscore
# names that init_cmd already calls; on ValueError surface as InitError.
from tripwire.core.init_github import (
    git_init as _git_init_core,
)
from tripwire.core.init_github import (
    record_repo_url_in_project_yaml as _record_repo_url_in_project_yaml,
)
from tripwire.core.init_github import (
    resolve_github_target as _resolve_github_target_core,
)
from tripwire.core.init_github import (
    setup_github_remote as _setup_github_remote_core,
)


def _git_init(target_dir: Path) -> None:
    """CLI wrapper — see :func:`tripwire.core.init_github.git_init`."""
    _git_init_core(target_dir, console=console)


def _resolve_github_target(
    target_dir: Path,
    *,
    github_owner: str | None,
    github_repo: str | None,
    token: str,
    non_interactive: bool,
) -> tuple[str, str]:
    """CLI wrapper — see :func:`tripwire.core.init_github.resolve_github_target`."""
    try:
        return _resolve_github_target_core(
            target_dir,
            github_owner=github_owner,
            github_repo=github_repo,
            token=token,
            non_interactive=non_interactive,
        )
    except ValueError as exc:
        raise InitError(str(exc)) from exc


def _setup_github_remote(
    target_dir: Path,
    *,
    no_github_repo: bool,
    no_push: bool,
    public: bool,
    github_owner: str | None,
    github_repo: str | None,
    non_interactive: bool,
) -> str | None:
    """CLI wrapper — see :func:`tripwire.core.init_github.setup_github_remote`."""
    try:
        return _setup_github_remote_core(
            target_dir,
            no_github_repo=no_github_repo,
            no_push=no_push,
            public=public,
            github_owner=github_owner,
            github_repo=github_repo,
            non_interactive=non_interactive,
            console=console,
        )
    except ValueError as exc:
        raise InitError(str(exc)) from exc


# ============================================================================
# The command
# ============================================================================


def _link_to_workspace(
    *,
    target_dir: Path,
    workspace_path: Path,
    key_prefix: str,
    project_name: str,
    copy_nodes: str | None,
) -> None:
    """CLI wrapper — see :func:`tripwire.core.init_workspace.link_to_workspace`."""
    from tripwire.core.init_workspace import link_to_workspace

    try:
        link_to_workspace(
            target_dir=target_dir,
            workspace_path=workspace_path,
            key_prefix=key_prefix,
            project_name=project_name,
            copy_nodes=copy_nodes,
            console=console,
        )
    except ValueError as exc:
        raise InitError(str(exc)) from exc


def _write_initial_readme(target_dir: Path) -> None:
    """Render the initial README for a freshly-init'd project.

    Failures are logged as warnings, not errors — a broken render
    shouldn't break init. Subsequent pushes to main will retry via the
    CD workflow.
    """
    from tripwire.core.readme_renderer import render

    try:
        rendered = render(target_dir, recent_merges=None)
    except Exception as exc:
        console.print(
            f"[yellow]Warning:[/yellow] could not render initial README ({exc}). "
            "The CD workflow will populate it on first push to main."
        )
        return
    readme_path = target_dir / "README.md"
    readme_path.write_text(rendered, encoding="utf-8")
    console.print(f"  [green]+[/green] {readme_path.relative_to(target_dir)}")


@click.command(name="init")
@click.argument(
    "target",
    type=click.Path(path_type=Path),
    required=False,
    default=".",
)
@click.option("--name", help="Project name (default: target directory basename).")
@click.option(
    "--key-prefix",
    help="Issue key prefix (e.g. SEI, PKB). Uppercase letters + digits.",
)
@click.option(
    "--base-branch",
    help="Default base branch [default: main].",
)
@click.option(
    "--repos",
    help="Comma-separated GitHub slugs (e.g. SeidoAI/backend,SeidoAI/frontend).",
)
@click.option(
    "--description",
    help="One-line project description.",
    default="",
)
@click.option("--no-git", is_flag=True, help="Skip `git init`.")
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing project.yaml in the target directory.",
)
@click.option(
    "--non-interactive",
    is_flag=True,
    help="Fail instead of prompting for missing required options.",
)
@click.option(
    "--workspace",
    "workspace_path",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=None,
    help=(
        "Path to a tripwire workspace to link this project to (v0.6b). "
        "After init, the project.yaml gains a workspace pointer and the "
        "workspace.yaml gains a project entry."
    ),
)
@click.option(
    "--copy-nodes",
    default=None,
    help=(
        "Comma-separated workspace node ids to copy into the project "
        "after linking. Only valid with --workspace."
    ),
)
@click.option(
    "--no-github-repo",
    is_flag=True,
    help=(
        "Don't create the GitHub project-tracking repo via the API. "
        "The remote is still configured (operator pre-created the repo, "
        "e.g. via Terraform)."
    ),
)
@click.option(
    "--no-remote",
    is_flag=True,
    help=(
        "Skip GitHub remote setup entirely (pre-v0.7.6 behaviour). "
        "Useful for local-only / experimental projects."
    ),
)
@click.option(
    "--no-push",
    is_flag=True,
    help=(
        "Configure the GitHub remote but don't push the initial commit. "
        "Leaves origin cold; useful when network is flaky."
    ),
)
@click.option(
    "--public",
    is_flag=True,
    help=(
        "Create the project-tracking repo as public. Default is private "
        "(project-tracking repos contain raw plans / decisions / agent "
        "transcripts)."
    ),
)
@click.option(
    "--github-owner",
    default=None,
    help=(
        "GitHub owner (user or org) for the project-tracking repo. "
        "Defaults to the authenticated user."
    ),
)
@click.option(
    "--github-repo",
    default=None,
    help=(
        "GitHub repo name for the project-tracking repo. "
        "Defaults to the target directory's basename."
    ),
)
def init_cmd(
    target: Path,
    name: str | None,
    key_prefix: str | None,
    base_branch: str | None,
    repos: str | None,
    description: str,
    no_git: bool,
    force: bool,
    non_interactive: bool,
    workspace_path: Path | None,
    copy_nodes: str | None,
    no_github_repo: bool,
    no_remote: bool,
    no_push: bool,
    public: bool,
    github_owner: str | None,
    github_repo: str | None,
) -> None:
    """Initialise a new tripwire in TARGET (or the current directory).

    Interactive by default — any missing required option is prompted. Pass
    --non-interactive to fail fast when flags are missing (for scripts).
    """
    target_dir = target.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # --force implies --non-interactive — scripted use shouldn't prompt.
    if force:
        non_interactive = True

    existing_project_yaml = target_dir / "project.yaml"
    if existing_project_yaml.exists() and not force:
        if non_interactive:
            raise InitError(
                f"{existing_project_yaml} already exists. Use --force to overwrite."
            )
        if not click.confirm(
            f"{existing_project_yaml} already exists. Overwrite?",
            default=False,
        ):
            raise InitError("Aborted by user.")
        force = True

    # ------------------------------------------------------------------
    # Collect config
    # ------------------------------------------------------------------

    if name is None:
        if non_interactive:
            # Default to the target directory basename. Matches the
            # interactive behaviour where that's offered as the prompt
            # default.
            name = target_dir.name
        else:
            name = _prompt_for_name(default=target_dir.name)

    if key_prefix is None:
        # Auto-extract from the project name. In interactive mode the
        # extracted value becomes the prompt default (user can Enter to
        # accept or type a different value). In non-interactive mode the
        # extracted value is used silently; we only error out if the
        # extraction fails (e.g. name starts with a digit).
        extracted = _extract_key_prefix(name)
        if non_interactive:
            if extracted is None:
                raise InitError(
                    f"Could not auto-extract a key prefix from name "
                    f"{name!r}. Pass --key-prefix explicitly."
                )
            key_prefix = extracted
        else:
            key_prefix = _prompt_for_key_prefix(default=extracted)
    else:
        key_prefix = _validate_key_prefix(key_prefix)

    if base_branch is None:
        base_branch = _prompt_for_base_branch("main") if not non_interactive else "main"

    if repos is None:
        repos_list = _prompt_for_repos() if not non_interactive else []
    else:
        repos_list = _parse_repos(repos)

    # Collect a `local:` path per slug (interactive only). Non-interactive
    # mode defaults to null per slug so the project.yaml is still valid;
    # spawn will fail with a clear message telling the user to fill it in.
    if repos_list and not non_interactive:
        repos_locals = _prompt_for_repo_locals(repos_list, target_dir)
    else:
        repos_locals = dict.fromkeys(repos_list)

    # Git init is on by default. `--no-git` skips it deterministically.
    # In interactive mode without an explicit flag, the default behaviour
    # is to init a git repo — we don't prompt because the answer is
    # almost always "yes" and the --no-git flag is available for the
    # rare exception.
    do_git = not no_git

    from tripwire import __version__ as _tripwire_version

    context = {
        "project_name": name,
        "key_prefix": key_prefix,
        "base_branch": base_branch,
        "description": description,
        "repos": repos_list,
        "repos_locals": repos_locals,
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
        "tripwire_version": _tripwire_version,
        # Filled in below by `_setup_github_remote` if remote setup runs.
        # The Jinja template emits the field conditionally, so None ⇒ omit.
        "project_repo_url": None,
    }

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    console.print(
        Panel.fit(
            f"[bold]Creating tripwire at[/bold] {target_dir}\n"
            f"name: {name}\n"
            f"key prefix: {key_prefix}\n"
            f"base branch: {base_branch}\n"
            f"repos: {', '.join(repos_list) if repos_list else '(none)'}",
            title="tripwire init",
            border_style="cyan",
        )
    )

    # ------------------------------------------------------------------
    # Write files
    # ------------------------------------------------------------------

    templates_dir = get_templates_dir()
    written = _copy_templates(templates_dir, target_dir, context)
    created_dirs = _create_project_dirs(target_dir)

    for path in written:
        rel = path.relative_to(target_dir)
        console.print(f"  [green]+[/green] {rel}")
    for path in created_dirs:
        rel = path.relative_to(target_dir)
        console.print(f"  [green]+[/green] {rel}/")

    # KUI-110: plant `.claude/settings.json` so the PostToolUse
    # validate-on-edit hook fires from day zero. Idempotent — if a
    # template already wrote `.claude/settings.json`, the helper merges
    # our entry rather than overwriting.
    from tripwire.cli.hooks import install_settings_into

    settings_path = install_settings_into(target_dir)
    console.print(f"  [green]+[/green] {settings_path.relative_to(target_dir)}")

    # ------------------------------------------------------------------
    # Git init
    # ------------------------------------------------------------------

    if do_git:
        _git_init(target_dir)
        console.print("  [green]+[/green] .git/ (git init + git add)")
    else:
        console.print("  [dim](skipped git init)[/dim]")

    # ------------------------------------------------------------------
    # GitHub remote setup (v0.7.6 item A)
    # ------------------------------------------------------------------

    # Remote setup needs git to be initialised. `--no-git` or `--no-remote`
    # both skip cleanly.
    if do_git and not no_remote:
        ssh_url = _setup_github_remote(
            target_dir,
            no_github_repo=no_github_repo,
            no_push=no_push,
            public=public,
            github_owner=github_owner,
            github_repo=github_repo,
            non_interactive=non_interactive,
        )
        if ssh_url:
            _record_repo_url_in_project_yaml(target_dir, ssh_url)
            console.print(f"  [green]+[/green] origin {ssh_url}")
    elif no_remote:
        console.print("  [dim](skipped GitHub remote setup --no-remote)[/dim]")

    # ------------------------------------------------------------------
    # Workspace link (v0.6b)
    # ------------------------------------------------------------------

    if copy_nodes and workspace_path is None:
        raise InitError("--copy-nodes requires --workspace")

    if workspace_path is not None:
        _link_to_workspace(
            target_dir=target_dir,
            workspace_path=workspace_path.expanduser().resolve(),
            key_prefix=key_prefix,
            project_name=name,
            copy_nodes=copy_nodes,
        )

    # ------------------------------------------------------------------
    # Initial README — render once so the project's GitHub repo page
    # carries something useful from day zero, not the (now-missing)
    # default README scaffold.
    # ------------------------------------------------------------------

    _write_initial_readme(target_dir)

    # ------------------------------------------------------------------
    # Next steps
    # ------------------------------------------------------------------

    console.print()
    console.print("[bold green]Done.[/bold green] Next steps:")
    if target_dir != Path.cwd():
        console.print(f"  cd {target_dir}")
    console.print("  claude")
    console.print()
    console.print("Then in Claude Code, start scoping with:")
    console.print("  [cyan]/pm-scope[/cyan] Describe what you want built.")
    console.print()
    console.print(
        "[dim]Drop raw planning docs in [/dim][cyan]./plans/[/cyan]"
        "[dim] first — /pm-scope reads them automatically.[/dim]"
    )
    console.print()
    console.print(
        "See [dim].claude/commands/[/dim] for the full list of "
        "[cyan]/pm-*[/cyan] slash commands."
    )
