"""Tripwire hook commands.

Two distinct verbs live here:

- ``tripwire hook validate-on-edit`` (singular) — the Claude Code
  PostToolUse handler. Reads the hook envelope from stdin, runs
  ``tripwire validate`` in-process (strict-by-default), and emits a
  ``decision: "block"`` JSON to stdout if the edit produced an invalid
  state. All defensive paths exit 0 silently so the hook never breaks
  unrelated agent work.

- ``tripwire hooks install`` (plural) — operator-facing retrofit. Drops
  ``.claude/settings.json`` (or merges the hooks block into an existing
  one) so an existing project picks up the edit-time hook without
  re-running ``tripwire init``.

Both commands share the same ``settings.json.j2`` template + the same
deep-merge helper, exposed below for use by ``tripwire init`` and
``tripwire session spawn``.
"""

from __future__ import annotations

import copy
import json
import logging
import sys
import threading
from importlib.resources import files
from pathlib import Path
from typing import Any

import click

from tripwire.core.validator import validate_project

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Shared template + merge logic (also imported by init / spawn)
# ----------------------------------------------------------------------


CLAUDE_SETTINGS_DIR_NAME = ".claude"
CLAUDE_SETTINGS_FILE_NAME = "settings.json"
HOOK_COMMAND = "tripwire hook validate-on-edit"


def load_template_settings() -> dict[str, Any]:
    """Load the packaged ``.claude/settings.json.j2`` as a dict.

    The template ships under ``tripwire.templates.claude`` with a ``.j2``
    suffix to reserve space for future per-project Jinja-rendered
    settings. Today there are no variables — read the bytes verbatim.
    """
    template = files("tripwire.templates.claude") / "settings.json.j2"
    content = template.read_text(encoding="utf-8")
    return json.loads(content)


def _hook_already_present(settings: dict[str, Any]) -> bool:
    """True iff our PostToolUse `validate-on-edit` entry is already wired."""
    post_tool_use = settings.get("hooks", {}).get("PostToolUse", [])
    if not isinstance(post_tool_use, list):
        return False
    for block in post_tool_use:
        if not isinstance(block, dict):
            continue
        for h in block.get("hooks", []) or []:
            if isinstance(h, dict) and HOOK_COMMAND in str(h.get("command", "")):
                return True
    return False


def _merge_hook_into_settings(
    existing: dict[str, Any], template: dict[str, Any]
) -> dict[str, Any]:
    """Append our PostToolUse entry into ``existing`` if not already there.

    Preserves every key on ``existing`` (env, permissions, other hooks).
    Only appends to ``hooks.PostToolUse``; never duplicates an existing
    matching entry.
    """
    result = copy.deepcopy(existing)
    template_hooks = template.get("hooks", {})

    if not template_hooks:
        return result

    result_hooks = result.setdefault("hooks", {})
    for event_name, template_blocks in template_hooks.items():
        existing_blocks = list(result_hooks.get(event_name, []))
        for tmpl_block in template_blocks:
            tmpl_command = ""
            for h in tmpl_block.get("hooks", []) or []:
                tmpl_command = str(h.get("command", ""))
                break
            already = False
            for ex_block in existing_blocks:
                for h in ex_block.get("hooks", []) or []:
                    if str(h.get("command", "")) == tmpl_command:
                        already = True
                        break
                if already:
                    break
            if not already:
                existing_blocks.append(copy.deepcopy(tmpl_block))
        result_hooks[event_name] = existing_blocks
    return result


def install_settings_into(project_dir: Path, *, force: bool = False) -> Path:
    """Plant or merge the PostToolUse hook into ``<project>/.claude/settings.json``.

    Idempotent without ``force``: if the hook entry is already present,
    the file is left untouched. With ``force`` the entire ``hooks`` key
    is replaced by the template's; sibling keys (env, permissions, etc.)
    are preserved.

    Returns the path of the settings file written.
    """
    settings_dir = project_dir / CLAUDE_SETTINGS_DIR_NAME
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / CLAUDE_SETTINGS_FILE_NAME

    template = load_template_settings()

    if not settings_path.is_file():
        settings_path.write_text(
            json.dumps(template, indent=2) + "\n", encoding="utf-8"
        )
        return settings_path

    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
        if not isinstance(existing, dict):
            existing = {}
    except json.JSONDecodeError:
        existing = {}

    if force:
        merged = {**existing, "hooks": copy.deepcopy(template.get("hooks", {}))}
    else:
        if _hook_already_present(existing):
            return settings_path
        merged = _merge_hook_into_settings(existing, template)

    settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return settings_path


# ----------------------------------------------------------------------
# Path-pattern matching for `validate-on-edit`
# ----------------------------------------------------------------------


_SESSION_ARTIFACTS = frozenset(
    {
        "session.yaml",
        "pm-response.yaml",
        "developer.md",
        "verified.md",
        "self-review.md",
        "decisions.md",
    }
)


def _is_tripwire_artifact(path: str) -> bool:
    """True if ``path`` is an editable tripwire artifact.

    Match by basename + parent-dir name (not absolute globs) so the same
    function works regardless of where the project root sits in the
    filesystem.
    """
    p = Path(path)
    name = p.name

    # sessions/<sid>/<file>
    if name in _SESSION_ARTIFACTS and p.parent.parent.name == "sessions":
        return True

    # issues/<key>/issue.yaml
    if name == "issue.yaml" and p.parent.parent.name == "issues":
        return True

    # nodes/**/*.yaml — anywhere a `nodes` dir appears in the path.
    if p.suffix == ".yaml":
        for parent in p.parents:
            if parent.name == "nodes":
                return True

    # project.yaml
    if name == "project.yaml":
        return True

    # graph/index.yaml
    if name == "index.yaml" and p.parent.name == "graph":
        return True

    return False


def _find_project_root(start: Path) -> Path | None:
    """Walk up from ``start`` looking for a directory containing ``project.yaml``."""
    p = start.resolve() if start.exists() else start
    if p.is_file():
        p = p.parent
    while True:
        if (p / "project.yaml").is_file():
            return p.resolve()
        if p.parent == p:
            return None
        p = p.parent


# ----------------------------------------------------------------------
# `tripwire hook validate-on-edit`
# ----------------------------------------------------------------------


@click.group(name="hook")
def hook_cmd() -> None:
    """Hook implementations invoked by Claude Code via .claude/settings.json."""


@hook_cmd.command("validate-on-edit")
@click.option(
    "--timeout-seconds",
    default=10,
    type=int,
    show_default=True,
    help="Maximum seconds to spend on validation; exits 0 silently on overrun.",
)
def validate_on_edit_cmd(timeout_seconds: int) -> None:
    """PostToolUse hook: run validate after each edit and emit block JSON on errors.

    Reads the Claude Code hook envelope from stdin. Exits 0 in every
    defensive path so a hook bug never blocks unrelated agent work.
    """
    try:
        raw = sys.stdin.read()
    except Exception as exc:  # pragma: no cover — stdin failures are rare
        click.echo(f"tripwire hook: stdin read failed: {exc}", err=True)
        return

    try:
        envelope = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return

    tool_input = envelope.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return

    if not _is_tripwire_artifact(str(file_path)):
        return

    abs_path = Path(file_path)
    if not abs_path.is_absolute():
        cwd = envelope.get("cwd")
        if cwd:
            abs_path = Path(cwd) / abs_path

    project_root = _find_project_root(abs_path)
    if project_root is None:
        return

    report_holder: list[Any] = [None]
    error_holder: list[BaseException | None] = [None]

    def _run() -> None:
        try:
            report_holder[0] = validate_project(project_root, strict=True, fix=False)
        except BaseException as exc:
            error_holder[0] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    if thread.is_alive():
        click.echo(
            f"tripwire hook: validation exceeded {timeout_seconds}s timeout; skipping",
            err=True,
        )
        return
    if error_holder[0] is not None:
        click.echo(
            f"tripwire hook: validation raised {type(error_holder[0]).__name__}: "
            f"{error_holder[0]}",
            err=True,
        )
        return

    report = report_holder[0]
    if report is None or not report.errors:
        return

    try:
        rel = str(abs_path.resolve().relative_to(project_root))
    except ValueError:
        rel = str(abs_path)

    formatted_errors = "\n".join(
        f"  - [{e.code}] {e.file or ''}: {e.message}" for e in report.errors[:20]
    )
    if len(report.errors) > 20:
        formatted_errors += f"\n  …and {len(report.errors) - 20} more"

    reason = (
        f"tripwire validate failed after edit to {rel}:\n\n"
        f"{formatted_errors}\n\n"
        f"Re-read the file, fix the validation errors, and re-edit."
    )
    click.echo(json.dumps({"decision": "block", "reason": reason}))


# ----------------------------------------------------------------------
# `tripwire hooks install`
# ----------------------------------------------------------------------


@click.group(name="hooks")
def hooks_cmd() -> None:
    """Hook management commands (install / upgrade)."""


@hooks_cmd.command("install")
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing hooks block instead of merging.",
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root (the directory containing project.yaml).",
)
def hooks_install_cmd(force: bool, project_dir: Path) -> None:
    """Plant or upgrade the Claude Code PostToolUse hook in this project.

    Idempotent without ``--force``: the file is rewritten only if our
    hook entry is missing. With ``--force`` the entire ``hooks`` key is
    overwritten by the packaged template; sibling keys are preserved.
    """
    resolved = project_dir.expanduser().resolve()
    if not (resolved / "project.yaml").is_file():
        raise click.ClickException(f"No project.yaml at {resolved}.")
    settings_path = install_settings_into(resolved, force=force)
    click.echo(f"  + {settings_path.relative_to(resolved)}")
