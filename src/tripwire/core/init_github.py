"""GitHub remote setup for ``tripwire init`` (v0.7.6 §2.A).

Resolves the target GitHub repo, creates it if missing, attaches it as
``origin``, and pushes the initial commit. Also owns the local
``git init`` step and the short-HEAD helper used elsewhere.

The CLI wrapper at ``cli/init.py`` calls these from `init_cmd`; on
failure they raise :class:`ValueError` (or call :func:`click.prompt`,
the one click coupling that's intrinsic to interactive resolution).
The CLI converts ValueErrors into :class:`InitError` for user-facing
output.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
from rich.console import Console

from tripwire.core import github_client


def git_init(target_dir: Path, *, console: Console | None = None) -> None:
    """Run ``git init`` and ``git add .`` in *target_dir*.

    Failures are reported via *console* (default Rich) as warnings, not
    errors — a user can always run ``git init`` manually afterwards.
    """
    if console is None:
        console = Console()
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


def resolve_github_target(
    target_dir: Path,
    *,
    github_owner: str | None,
    github_repo: str | None,
    token: str,
    non_interactive: bool,
) -> tuple[str, str]:
    """Resolve ``(owner, name)`` for the project-tracking repo.

    Defaults: owner = the authenticated user behind ``token``, name =
    the target directory's basename. Either can be overridden by flag.
    Interactive mode confirms the result via :func:`click.prompt`.

    Raises:
        ValueError: non-interactive mode + no resolvable owner, or
            interactive mode received an invalid ``<owner>/<name>``
            slug.
    """
    name = github_repo or target_dir.name
    owner = github_owner or github_client._authenticated_owner(token) or ""

    if non_interactive:
        if not owner:
            raise ValueError(
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
        raise ValueError(
            f"Invalid GitHub slug {full!r}; expected `<owner>/<name>` (e.g. "
            "alice/my-project)."
        )
    owner, name = full.split("/", 1)
    if not owner or not name:
        raise ValueError(f"Invalid GitHub slug {full!r}; both parts required.")
    return owner, name


def setup_github_remote(
    target_dir: Path,
    *,
    no_github_repo: bool,
    no_push: bool,
    public: bool,
    github_owner: str | None,
    github_repo: str | None,
    non_interactive: bool,
    console: Console | None = None,
) -> str | None:
    """Create or attach the GitHub project-tracking repo and configure git.

    Implements v0.7.6 spec §2.A.1 steps 2-5:

    1. Resolve the GitHub target (owner + name).
    2. Check whether the repo exists.
    3. Create it if missing (unless ``no_github_repo``).
    4. Add the remote.
    5. Push the initial commit (unless ``no_push``).

    Raises :class:`ValueError` if no GitHub token is resolvable.
    Returns the SSH URL the remote was configured with.
    """
    if console is None:
        console = Console()
    token = github_client.resolve_token()
    if token is None:
        raise ValueError(
            "No GitHub token found. Set GITHUB_TOKEN, run `gh auth login`, "
            "or pass --no-remote to skip remote setup."
        )

    owner, name = resolve_github_target(
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
    git_set_remote(target_dir, ssh_url)

    # Step 5: push the initial commit, unless opted out.
    if not no_push:
        git_initial_commit_and_push(target_dir, console=console)

    return ssh_url


def git_set_remote(target_dir: Path, ssh_url: str) -> None:
    """Add the ``origin`` remote, switching url if already set.

    Robust to operators who ran ``git remote add origin ...`` themselves
    before re-running init — ``set-url`` overwrites without complaint.
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


def git_initial_commit_and_push(
    target_dir: Path, *, console: Console | None = None
) -> None:
    """Create the initial commit (if absent) and push to ``origin/main``.

    ``git init`` + ``git add .`` already happened in :func:`git_init`;
    this seals it with a commit and pushes. Failures are surfaced as
    warnings via *console*, not exceptions — the operator can finish
    manually if push fails for network reasons.
    """
    if console is None:
        console = Console()
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


def record_repo_url_in_project_yaml(target_dir: Path, ssh_url: str) -> None:
    """Write ``project_repo_url: <url>`` into the freshly-stamped project.yaml.

    The Jinja template emits the line conditionally on the context dict;
    by the time we know the URL, the file is already written. Append
    rather than re-render to keep the change minimal and side-effect-free.
    """
    from tripwire.core.store import load_project, save_project

    cfg = load_project(target_dir)
    cfg = cfg.model_copy(update={"project_repo_url": ssh_url})
    save_project(target_dir, cfg)


def git_head_short(repo_dir: Path) -> str:
    """Return short SHA of HEAD in a git repo."""
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
