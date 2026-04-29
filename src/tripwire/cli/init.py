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
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from rich.console import Console
from rich.panel import Panel

from tripwire.core import github_client, paths
from tripwire.templates import get_templates_dir

KEY_PREFIX_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*$")
CREATED_DIRS = [
    paths.ISSUES_DIR,
    paths.NODES_DIR,
    paths.SESSIONS_DIR,
    paths.PLANS_DIR,
]
PROJECT_TEMPLATE_SUBDIR = "project"

# Template subdirectories that get Jinja2-rendered at init time.
# Files under these directories are RENDERED through Jinja with the
# project context (project_name, key_prefix, etc.) and the `.j2` suffix
# is stripped in the destination filename.
JINJA_RENDERED_SUBDIRS: tuple[str, ...] = (PROJECT_TEMPLATE_SUBDIR,)

# Mapping from source subdirectory under `templates/` to destination
# relative path under the project root. Files are copied verbatim
# (including any `.j2` suffix — agents render these at runtime).
#
# `project` is handled separately because its files are rendered into
# the project root.
#
# `agent_templates` → `agents` is a rename (the source name is clearer
# for the package, but the destination name matches the rest of the
# plan's layout).
#
# `artifacts` is the one exception that stays nested under `templates/`
# in the destination — it's the set of templates that SESSIONS use to
# produce their session artifacts at runtime.
VERBATIM_TEMPLATE_MAPPINGS: tuple[tuple[str, str], ...] = (
    ("enums", "enums"),
    ("issue_templates", "issue_templates"),
    ("comment_templates", "comment_templates"),
    ("artifacts", "templates/artifacts"),
    ("scoping-artifacts", "plans/artifacts"),
    ("agent_templates", "agents"),
    ("session_templates", "session_templates"),
    ("orchestration", "orchestration"),
    ("skills", ".claude/skills"),
    ("commands", ".claude/commands"),
)

# Standalone files (at `templates/` root, not under a subdirectory) that
# should be rendered into the project root. `standards.md.j2` is the
# only one in v0.
ROOT_J2_FILES: tuple[tuple[str, str], ...] = (("standards.md.j2", "standards.md"),)

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


# ============================================================================
# Template rendering and copying
# ============================================================================


def _jinja_env(templates_dir: Path) -> Environment:
    """Construct a Jinja2 environment rooted at the templates directory.

    `StrictUndefined` catches typos in template variables — better to fail
    the init than silently produce a file with `{{ missing_var }}`.
    """
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )


def _copy_templates(
    templates_dir: Path, target_dir: Path, context: dict[str, Any]
) -> list[Path]:
    """Copy the packaged templates tree into the target.

    Three distinct code paths:

    1. **Jinja-rendered subdirs** (`templates/project/*`): files with a
       `.j2` suffix are rendered through Jinja with the init context and
       the suffix is stripped. Other files are copied verbatim.

    2. **Verbatim subdirs** (`templates/enums/`, `templates/issue_templates/`,
       etc.): files are copied as-is. `.j2` files keep their suffix
       because agents render them at runtime. The source subdir name may
       map to a different destination name (see `VERBATIM_TEMPLATE_MAPPINGS`).

    3. **Root-level files** (`templates/standards.md.j2`): Jinja-rendered
       into the project root per `ROOT_J2_FILES`.

    `__init__.py` markers are never copied into target projects.
    """
    env = _jinja_env(templates_dir)
    written: list[Path] = []

    # 1. Jinja-rendered subdirs (currently only `project/`).
    for subdir in JINJA_RENDERED_SUBDIRS:
        source_root = templates_dir / subdir
        if not source_root.is_dir():
            raise InitError(
                f"Packaged templates directory missing: {source_root}. "
                "This is a package installation problem."
            )
        for source in sorted(source_root.rglob("*")):
            if source.is_dir() or source.name == "__init__.py":
                continue
            rel = source.relative_to(source_root)
            dest = target_dir / _map_destination(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".j2":
                template_name = str(Path(subdir) / rel)
                rendered = env.get_template(template_name).render(**context)
                dest.write_text(rendered, encoding="utf-8")
            else:
                shutil.copy2(source, dest)
            written.append(dest)

    # 2. Verbatim subdirs — copied as-is, with optional rename.
    for src_subdir, dest_subdir in VERBATIM_TEMPLATE_MAPPINGS:
        source_root = templates_dir / src_subdir
        if not source_root.is_dir():
            # Subdir doesn't exist yet (e.g. `skills` before Step 10).
            continue
        dest_root = target_dir / dest_subdir
        for source in sorted(source_root.rglob("*")):
            if source.is_dir() or source.name == "__init__.py":
                continue
            rel = source.relative_to(source_root)
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            written.append(dest)

    # 3. Root-level Jinja files.
    for src_name, dest_name in ROOT_J2_FILES:
        source = templates_dir / src_name
        if not source.is_file():
            continue
        dest = target_dir / dest_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        rendered = env.get_template(src_name).render(**context)
        dest.write_text(rendered, encoding="utf-8")
        written.append(dest)

    return written


def _map_destination(rel: Path) -> Path:
    """Translate a template-relative path to its destination path.

    - `gitignore.j2` → `.gitignore`
    - `foo.yaml.j2` → `foo.yaml`
    - `foo.md.j2` → `foo.md`
    - Everything else: strip the `.j2` extension if present.
    """
    if rel.name == "gitignore.j2":
        return rel.with_name(".gitignore")
    if rel.suffix == ".j2":
        return rel.with_suffix("")
    return rel


def _create_project_dirs(target_dir: Path) -> list[Path]:
    """Create the empty project subdirectories with `.gitkeep` markers."""
    created: list[Path] = []
    for rel in CREATED_DIRS:
        dir_path = target_dir / rel
        dir_path.mkdir(parents=True, exist_ok=True)
        gitkeep = dir_path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
        created.append(dir_path)
    return created


# ============================================================================
# Git init
# ============================================================================


def _git_init(target_dir: Path) -> None:
    """Run `git init` and `git add` in the target directory.

    Failures are reported as warnings, not errors — a user can always run
    `git init` manually afterwards.
    """
    try:
        subprocess.run(
            ["git", "init", "--initial-branch=main"],
            cwd=target_dir,
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        console.print(
            f"[yellow]Warning:[/yellow] git init failed ({exc}). "
            "Run `git init` manually if you want version control."
        )
        return
    # Stage the initial tree so the user can commit immediately.
    subprocess.run(
        ["git", "add", "."],
        cwd=target_dir,
        capture_output=True,
        check=False,
    )


# ============================================================================
# GitHub remote setup (v0.7.6 item A)
# ============================================================================


def _resolve_github_target(
    target_dir: Path,
    *,
    github_owner: str | None,
    github_repo: str | None,
    token: str,
    non_interactive: bool,
) -> tuple[str, str]:
    """Resolve `(owner, name)` for the project-tracking repo.

    Defaults: owner = the authenticated user behind ``token``, name =
    the target directory's basename. Either can be overridden by flag.
    Interactive mode confirms the result via prompt.
    """
    name = github_repo or target_dir.name
    owner = github_owner or github_client._authenticated_owner(token) or ""

    if non_interactive:
        if not owner:
            raise InitError(
                "Could not determine GitHub owner. Pass --github-owner "
                "explicitly or check that your token has user-read scope."
            )
        return owner, name

    full = click.prompt(
        "GitHub project-tracking repo (<owner>/<name>)",
        default=f"{owner}/{name}" if owner else "",
        type=str,
    ).strip()
    if "/" not in full:
        raise InitError(
            f"Invalid GitHub slug {full!r}; expected `<owner>/<name>` (e.g. "
            "alice/my-project)."
        )
    owner, name = full.split("/", 1)
    if not owner or not name:
        raise InitError(f"Invalid GitHub slug {full!r}; both parts required.")
    return owner, name


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
    """Create or attach the GitHub project-tracking repo and configure git.

    Implements v0.7.6 spec §2.A.1 steps 2-5:

    1. Resolve the GitHub target (owner + name).
    2. Check whether the repo exists.
    3. Create it if missing (unless ``no_github_repo``).
    4. Add the remote.
    5. Push the initial commit (unless ``no_push``).

    Returns the SSH URL the remote was configured with, or None if the
    flow short-circuited (caller already handled ``--no-remote``).
    """
    token = github_client.resolve_token()
    if token is None:
        raise InitError(
            "No GitHub token found. Set GITHUB_TOKEN, run `gh auth login`, "
            "or pass --no-remote to skip remote setup."
        )

    owner, name = _resolve_github_target(
        target_dir,
        github_owner=github_owner,
        github_repo=github_repo,
        token=token,
        non_interactive=non_interactive,
    )

    ssh_url = f"git@github.com:{owner}/{name}.git"

    if no_github_repo:
        # Operator pre-created the repo (Terraform / manual / org policy).
        # Skip the API check and the create call; just wire git up.
        console.print(
            f"  [dim]· Skipping GitHub API check (--no-github-repo); using "
            f"{owner}/{name}[/dim]"
        )
    else:
        if github_client.repo_exists(owner, name, token=token):
            console.print(f"  [dim]✓ Using existing GitHub repo {owner}/{name}[/dim]")
        else:
            visibility = "public" if public else "private"
            console.print(
                f"  [green]+[/green] Creating {visibility} GitHub repo {owner}/{name}"
            )
            response = github_client.create_repo(
                owner,
                name,
                private=not public,
                description=f"Tripwire project-tracking repo for {name}",
                token=token,
            )
            # Prefer the API-returned ssh_url so we honour any host
            # variation the caller has on their GitHub Enterprise install.
            ssh_url = response.get("ssh_url") or ssh_url

    # Step 4: add the remote (idempotent — `git remote set-url` if it
    # already points somewhere).
    _git_set_remote(target_dir, ssh_url)

    # Step 5: push the initial commit, unless opted out.
    if not no_push:
        _git_initial_commit_and_push(target_dir)

    return ssh_url


def _git_set_remote(target_dir: Path, ssh_url: str) -> None:
    """Add the `origin` remote, switching url if already set.

    Robust to operators who ran `git remote add origin ...` themselves
    before re-running init — `set-url` overwrites without complaint.
    """
    existing = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=target_dir,
        capture_output=True,
        check=False,
    )
    if existing.returncode == 0:
        subprocess.run(
            ["git", "remote", "set-url", "origin", ssh_url],
            cwd=target_dir,
            check=False,
            capture_output=True,
        )
    else:
        subprocess.run(
            ["git", "remote", "add", "origin", ssh_url],
            cwd=target_dir,
            check=False,
            capture_output=True,
        )


def _git_initial_commit_and_push(target_dir: Path) -> None:
    """Create the initial commit (if absent) and push to `origin/main`.

    `git init` + `git add .` already happened in `_git_init`; we just
    need to seal it with a commit and push. Failures are surfaced as
    warnings, not errors — the operator can finish manually if push
    fails for network reasons.
    """
    # Skip the commit if HEAD already points somewhere (re-runs).
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=target_dir,
        capture_output=True,
        check=False,
    )
    if head.returncode != 0:
        commit = subprocess.run(
            ["git", "commit", "-m", "Initial tripwire scaffold"],
            cwd=target_dir,
            capture_output=True,
            check=False,
        )
        if commit.returncode != 0:
            console.print(
                "[yellow]Warning:[/yellow] initial commit failed "
                f"({commit.stderr.decode(errors='replace').strip()}). "
                "Commit and push manually: "
                "`git commit -m 'init' && git push -u origin main`."
            )
            return

    push = subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=target_dir,
        capture_output=True,
        check=False,
    )
    if push.returncode != 0:
        console.print(
            "[yellow]Warning:[/yellow] git push failed "
            f"({push.stderr.decode(errors='replace').strip()}). "
            "Push manually: `git push -u origin main`."
        )


def _record_repo_url_in_project_yaml(target_dir: Path, ssh_url: str) -> None:
    """Write `project_repo_url: <url>` into the freshly-stamped project.yaml.

    The Jinja template emits the line conditionally on the context dict;
    by the time we know the URL, the file is already written. Append
    rather than re-render to keep the change minimal and side-effect-free.
    """
    from tripwire.core.store import load_project, save_project

    cfg = load_project(target_dir)
    cfg = cfg.model_copy(update={"project_repo_url": ssh_url})
    save_project(target_dir, cfg)


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
    """Link the newly-init'd project to a workspace + optionally copy nodes.

    Uses the internal Python API directly (no subprocess / no ``uv``
    dependency) so this works in any install environment.
    """
    import os

    from tripwire.core.store import load_project as _load_project
    from tripwire.core.store import save_project as _save_project
    from tripwire.core.workspace_store import (
        add_project as _ws_add_project,
    )
    from tripwire.core.workspace_store import (
        workspace_exists as _ws_exists,
    )
    from tripwire.models.project import ProjectWorkspacePointer
    from tripwire.models.workspace import WorkspaceProjectEntry

    slug = key_prefix.lower()

    if not _ws_exists(workspace_path):
        raise InitError(f"No workspace.yaml at {workspace_path}")

    # Compute relative paths from each side.
    try:
        pointer_path = os.path.relpath(workspace_path, target_dir)
    except ValueError:
        pointer_path = str(workspace_path)
    try:
        ws_relative_back = os.path.relpath(target_dir, workspace_path)
    except ValueError:
        ws_relative_back = str(target_dir)

    # Write workspace-side FIRST so that if it fails (e.g. duplicate
    # slug) the project-side pointer hasn't been written yet — avoiding
    # a one-sided link.
    try:
        _ws_add_project(
            workspace_path,
            WorkspaceProjectEntry(
                slug=slug,
                name=project_name,
                path=ws_relative_back,
            ),
        )
    except ValueError as exc:
        raise InitError(f"Failed to register in workspace: {exc}") from exc

    cfg = _load_project(target_dir)
    cfg_new = cfg.model_copy(
        update={"workspace": ProjectWorkspacePointer(path=pointer_path)}
    )
    _save_project(target_dir, cfg_new)

    console.print(
        f"[dim]✓ Linked {project_name} to workspace at {workspace_path}[/dim]"
    )

    if copy_nodes:
        from datetime import datetime, timezone

        from tripwire.core.node_store import node_exists, save_node

        node_ids = [nid.strip() for nid in copy_nodes.split(",") if nid.strip()]
        head_sha = _git_head_short(workspace_path)
        copied = 0
        for nid in node_ids:
            if node_exists(target_dir, nid):
                console.print(
                    f"[yellow]⚠ {nid}: already exists locally, skipped[/yellow]"
                )
                continue
            try:
                from tripwire.core.parser import parse_frontmatter_body
                from tripwire.core.paths import workspace_node_path
                from tripwire.models.node import ConceptNode

                ws_node_path = workspace_node_path(workspace_path, nid)
                if not ws_node_path.is_file():
                    console.print(f"[yellow]⚠ {nid}: not found in workspace[/yellow]")
                    continue
                text = ws_node_path.read_text(encoding="utf-8")
                fm, _body = parse_frontmatter_body(text)
                canonical = ConceptNode.model_validate(fm)
                local_copy = canonical.model_copy(
                    update={
                        "origin": "workspace",
                        "scope": "workspace",
                        "workspace_sha": head_sha,
                        "workspace_pulled_at": datetime.now(tz=timezone.utc),
                    }
                )
                save_node(target_dir, local_copy, update_cache=False)
                copied += 1
            except Exception as exc:
                console.print(f"[yellow]⚠ {nid}: copy failed: {exc}[/yellow]")
        if copied:
            console.print(f"[dim]✓ Copied {copied} node(s) from workspace[/dim]")


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


def _git_head_short(repo_dir: Path) -> str:
    """Return short SHA of HEAD in a git repo."""
    import subprocess as _subprocess

    return _subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


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
