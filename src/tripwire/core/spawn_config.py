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

import warnings
from pathlib import Path
from typing import Any

import yaml

from tripwire.core.spawn_routing import RouteResolution, resolve_route
from tripwire.core.store import load_project
from tripwire.models.session import AgentSession
from tripwire.models.spawn import SpawnConfigValues, SpawnDefaults


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

    resolved = SpawnDefaults.model_validate(base)
    # KUI-94 §C4 — apply agent yaml's runtime field as a low-precedence
    # default. _apply_agent_yaml_overrides is a no-op when a project/
    # session layer already pinned invocation.runtime, so explicit user
    # config still wins.
    if session is not None and session.agent:
        _apply_agent_yaml_overrides(
            resolved, project_dir, agent_id=session.agent, session=session
        )
    _apply_provider_validation(resolved)
    return resolved


def _project_explicitly_pins_runtime(project_dir: Path) -> bool:
    """True iff project.yaml / .tripwire/spawn/defaults.yaml explicitly
    set ``invocation.runtime``. Used by ``_apply_agent_yaml_overrides``
    to decide whether the agent yaml's declared runtime is allowed to
    override (it is NOT — explicit project config wins)."""
    file_override = project_dir / ".tripwire" / "spawn" / "defaults.yaml"
    if file_override.is_file():
        try:
            data = yaml.safe_load(file_override.read_text(encoding="utf-8")) or {}
            inv = data.get("invocation") if isinstance(data, dict) else None
            if isinstance(inv, dict) and "runtime" in inv:
                return True
        except Exception:
            # Malformed override file — let the main loader surface it.
            pass
    try:
        proj = load_project(project_dir)
    except Exception:
        proj = None
    if proj is not None and proj.spawn_defaults:
        inv = (
            proj.spawn_defaults.get("invocation")
            if isinstance(proj.spawn_defaults, dict)
            else None
        )
        if isinstance(inv, dict) and "runtime" in inv:
            return True
    return False


def _apply_agent_yaml_overrides(
    resolved: SpawnDefaults,
    project_dir: Path,
    agent_id: str,
    session: AgentSession | None = None,
) -> None:
    """Apply agent yaml's declared ``runtime`` field to a resolved spawn
    config (KUI-94 §C4).

    Precedence: session.spawn_config > project layers > agent yaml >
    shipped default. The helper is a no-op when a higher layer has
    explicitly pinned ``invocation.runtime``; in that case the agent's
    declared runtime is silently shadowed.

    Mutates ``resolved`` in place. Tolerant of missing / malformed
    agent yamls — they're metadata, not load-bearing config.
    """
    agent_yaml = project_dir / "agents" / f"{agent_id}.yaml"
    if not agent_yaml.is_file():
        return
    try:
        data = yaml.safe_load(agent_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return
    if not isinstance(data, dict):
        return
    declared = data.get("runtime")
    # Defensive: legacy values like "claude-code" or typos are ignored.
    # Validation is the registry's job at spawn time, not ours.
    if declared not in ("claude", "codex"):
        return

    # Higher-precedence layers win: project file/inline OR an explicit
    # session.spawn_config.invocation.runtime (the loader already
    # applied that, but we can't tell from the resolved alone whether
    # the value came from a user pin or the shipped default).
    if _project_explicitly_pins_runtime(project_dir):
        return
    if (
        session is not None
        and session.spawn_config is not None
        and session.spawn_config.invocation is not None
        and "runtime" in session.spawn_config.invocation.model_fields_set
    ):
        return

    resolved.invocation.runtime = declared
    resolved.config.provider = declared
    # NOTE: callers (the loader, prep) run _apply_provider_validation
    # afterwards; we don't validate inline to avoid duplicate warnings
    # when the helper is invoked from inside the loader.


# Field defaults used to detect "user-set non-default" values on codex
# sessions. Computed once at module load so the comparison stays cheap.
_CONFIG_DEFAULTS = SpawnConfigValues()


def _apply_provider_validation(resolved: SpawnDefaults) -> None:
    """Codex sessions don't honour Claude-only flags. Warn-and-drop the
    ones that have no codex analogue (``disallowed_tools``,
    ``fallback_model``); warn-and-keep the ones we adapt at the runtime
    or monitor layer (``max_turns``, ``system_prompt_append``).

    Mutates ``resolved`` in place. Claude sessions are left alone.
    """
    if resolved.config.provider != "codex":
        return

    cfg = resolved.config

    if cfg.disallowed_tools:
        warnings.warn(
            "spawn_config: 'disallowed_tools' has no codex equivalent; "
            "value will be ignored. Resetting to []. "
            "(Provider-aware validation, KUI-94 §C3.)",
            stacklevel=2,
        )
        cfg.disallowed_tools = []

    if cfg.fallback_model:
        warnings.warn(
            "spawn_config: 'fallback_model' is claude-specific (auto-fallback "
            "to a smaller Anthropic model on transient failure); codex has no "
            "analogue. Clearing value. (KUI-94 §C3.)",
            stacklevel=2,
        )
        cfg.fallback_model = ""

    if cfg.max_turns != _CONFIG_DEFAULTS.max_turns:
        warnings.warn(
            "spawn_config: 'max_turns' is enforced by the in-flight monitor "
            "for codex sessions (no flag analogue); value preserved. "
            "(KUI-94 §C3.)",
            stacklevel=2,
        )

    if resolved.system_prompt_append.strip():
        warnings.warn(
            "spawn_config: 'system_prompt_append' is prepended to the user "
            "prompt for codex sessions (no --append-system-prompt flag); "
            "value preserved. (KUI-94 §C3.)",
            stacklevel=2,
        )


def render_prompt(defaults: SpawnDefaults, **ctx: Any) -> str:
    """Interpolate `{key}` placeholders in the prompt template."""
    return defaults.prompt_template.format(**ctx)


def render_system_append(defaults: SpawnDefaults, **ctx: Any) -> str:
    """Interpolate `{key}` placeholders in the system-prompt-append template."""
    return defaults.system_prompt_append.format(**ctx)


def render_resume_prompt(defaults: SpawnDefaults, **ctx: Any) -> str:
    """Interpolate `{key}` placeholders in the resume-prompt template.

    Used when re-spawning a paused/failed session — the new user turn
    is a brief continuation cue, not a full re-send of plan.md. Claude
    loads the prior conversation from its jsonl via ``--resume <uuid>``.
    """
    return defaults.resume_prompt_template.format(**ctx)


def build_claude_args(
    defaults: SpawnDefaults,
    *,
    prompt: str | None,
    system_append: str,
    session_id: str,
    claude_session_id: str,
    resume: bool = False,
    interactive: bool = False,
    project_dir: Path | None = None,
) -> list[str]:
    """Build the claude CLI argv from the resolved spawn config.

    When ``interactive=True``, the ``-p <prompt>`` pair is omitted so
    claude starts in interactive mode. ``prompt`` must be ``None`` in
    that case; the caller delivers the kickoff prompt via send-keys
    after the ready-probe.

    When ``resume=True``, ``--resume <claude_session_id>`` is appended
    and ``--session-id`` is omitted. Claude rejects the combination
    ``--session-id X --resume X`` unless ``--fork-session`` is also
    present; for same-session resume, ``--resume`` alone is correct.

    When ``resume=False``, ``--session-id <claude_session_id>`` is
    emitted so the session is addressable (and resumable later).

    ``session_id`` (tripwire's human slug) is passed as ``--name``
    unconditionally — it's display-only and safe in both modes.

    Flag set matches ``claude --help`` output and spec §8.1.

    v0.7.10 §3.A2 — when ``project_dir`` is supplied, the resolved
    spawn config's ``task_kind`` is looked up via
    :func:`tripwire.core.spawn_routing.resolve_route`. The route's
    ``(model, effort)`` replace ``cfg.model`` / ``cfg.effort`` (which
    become defaults that the route layers on top of). When
    ``project_dir`` is ``None``, the legacy path is preserved — every
    pre-routing test continues to pass without modification.
    """
    if interactive and prompt is not None:
        raise ValueError("prompt must be None when interactive=True")
    if not interactive and prompt is None:
        raise ValueError("prompt is required when interactive=False")

    cfg = defaults.config
    model = cfg.model
    effort = cfg.effort
    if project_dir is not None:
        route: RouteResolution = resolve_route(cfg.task_kind, project_dir)
        model = route.model
        effort = route.effort
    args: list[str] = [defaults.invocation.command]
    if not interactive:
        args += ["-p", prompt]
    args += ["--name", session_id]
    if resume:
        args += ["--resume", claude_session_id]
    else:
        args += ["--session-id", claude_session_id]
    args += [
        "--effort",
        effort,
        "--model",
        model,
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
    return args
