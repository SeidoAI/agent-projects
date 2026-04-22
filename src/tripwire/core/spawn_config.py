"""Resolve spawn configuration with precedence session > project > tripwire default.

Three sources stack onto the shipped default:
  1. `src/tripwire/templates/spawn/defaults.yaml` (tripwire default — always loaded)
  2. `<project>/.tripwire/spawn/defaults.yaml` (file-based project override)
  3. `project.yaml.spawn_defaults` (inline project override)
  4. `session.yaml.spawn_config` (per-session override — highest priority)

Each layer deep-merges into the prior; scalar/list values at a leaf key
replace the prior value entirely. Use `load_resolved_spawn_config` to get
a fully merged `SpawnDefaults` and then `build_claude_args` to emit the
Popen argv list.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tripwire.core.store import load_project
from tripwire.models.session import AgentSession
from tripwire.models.spawn import SpawnDefaults


def _shipped_path() -> Path:
    import tripwire

    return Path(tripwire.__file__).parent / "templates" / "spawn" / "defaults.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge `override` into `base`. Dicts recurse; other types replace."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_resolved_spawn_config(
    project_dir: Path,
    session: AgentSession | None = None,
) -> SpawnDefaults:
    """Resolve spawn config. Session > project-inline > project-file > default."""
    base: dict[str, Any] = (
        yaml.safe_load(_shipped_path().read_text(encoding="utf-8")) or {}
    )

    # 2. Project file override
    file_override = project_dir / ".tripwire" / "spawn" / "defaults.yaml"
    if file_override.is_file():
        override = yaml.safe_load(file_override.read_text(encoding="utf-8")) or {}
        base = _deep_merge(base, override)

    # 3. Project.yaml inline
    try:
        project = load_project(project_dir)
    except Exception:
        project = None
    if project is not None and project.spawn_defaults:
        base = _deep_merge(base, project.spawn_defaults)

    # 4. Session override
    if session is not None and session.spawn_config is not None:
        session_data = session.spawn_config.model_dump(exclude_none=True)
        # SpawnConfig dumps `invocation`/`config` as empty dicts by default; drop those
        # so they don't stomp the prior layer.
        session_data = {
            k: v for k, v in session_data.items() if v not in (None, {}, [])
        }
        base = _deep_merge(base, session_data)

    return SpawnDefaults.model_validate(base)


def render_prompt(defaults: SpawnDefaults, **ctx: Any) -> str:
    """Interpolate `{key}` placeholders in the prompt template."""
    return defaults.prompt_template.format(**ctx)


def render_system_append(defaults: SpawnDefaults, **ctx: Any) -> str:
    """Interpolate `{key}` placeholders in the system-prompt-append template."""
    return defaults.system_prompt_append.format(**ctx)


def build_claude_args(
    defaults: SpawnDefaults,
    *,
    prompt: str | None,
    system_append: str,
    session_id: str,
    claude_session_id: str,
    resume: bool = False,
    interactive: bool = False,
) -> list[str]:
    """Build the claude CLI argv from the resolved spawn config.

    When ``interactive=True``, the ``-p <prompt>`` pair is omitted so
    claude starts in interactive mode. ``prompt`` must be ``None`` in
    that case; the caller delivers the kickoff prompt via send-keys
    after the ready-probe.

    The two session identifiers are distinct:
    - ``session_id`` — tripwire's human-readable session slug, passed as
      ``--name`` (display label in claude's prompt box, /resume picker,
      and terminal title).
    - ``claude_session_id`` — claude's internal UUID identifier, passed
      as ``--session-id`` (required for ``--resume`` to work).

    Flag set matches ``claude --help`` output and spec §8.1.
    """
    if interactive and prompt is not None:
        raise ValueError("prompt must be None when interactive=True")
    if not interactive and prompt is None:
        raise ValueError("prompt is required when interactive=False")

    cfg = defaults.config
    args: list[str] = [defaults.invocation.command]
    if not interactive:
        args += ["-p", prompt]
    args += [
        "--name",
        session_id,
        "--session-id",
        claude_session_id,
        "--effort",
        cfg.effort,
        "--model",
        cfg.model,
        "--fallback-model",
        cfg.fallback_model,
        "--permission-mode",
        cfg.permission_mode,
        "--disallowedTools",
        ",".join(cfg.disallowed_tools),
        "--max-turns",
        str(cfg.max_turns),
        "--max-budget-usd",
        str(cfg.max_budget_usd),
        "--output-format",
        cfg.output_format,
        "--append-system-prompt",
        system_append,
    ]
    if resume:
        args.append("--resume")
    return args
