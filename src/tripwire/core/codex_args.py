"""Build the `codex exec [resume]` argv from a resolved spawn config.

Parallel to :func:`tripwire.core.spawn_config.build_claude_args`. Codex
CLI's flag surface differs in ways spelled out in the v0.7.10 spec
section 3.C:

  - ``--json`` is on (we tail JSONL via :mod:`tripwire.core.codex_stream`)
  - the prompt is a positional argument, not ``-p``
  - ``model_reasoning_effort`` is a ``-c`` config override (TOML), not a
    standalone flag
  - resume is a SUBCOMMAND (``codex exec resume <SESSION_ID>``), not a
    flag — verified against ``codex --help`` v0.125.0
  - ``--sandbox`` accepts read-only / workspace-write / danger-full-access

Several Claude-only flags have no Codex analogue; the spec calls these
"workaround in runtime" — currently:

  - ``--max-turns`` → enforced by counting messages in the JSONL stream
    (see :mod:`tripwire.runtimes.monitor` / ``codex_stream``)
  - ``--max-budget-usd`` → enforced by summing usage events in the stream
  - ``--append-system-prompt`` → prepended to the user prompt at invoke
  - ``--disallowedTools`` → not enforceable on codex (warn at config-
    resolve time; see :mod:`tripwire.core.spawn_config`)
  - ``--fallback-model`` → simple retry-with-Y on error (deferred)
"""

from __future__ import annotations

from tripwire.models.spawn import SpawnDefaults


def build_codex_args(
    defaults: SpawnDefaults,
    *,
    prompt: str | None,
    system_append: str,
    session_id: str,
    codex_session_id: str,
    resume: bool = False,
    interactive: bool = False,
) -> list[str]:
    """Build the codex CLI argv from the resolved spawn config.

    Two modes:

    - First-spawn (``resume=False``): ``codex exec --json -m MODEL
      -c model_reasoning_effort="EFFORT" --sandbox <mode> "<PROMPT>"``.
    - Resume (``resume=True``): ``codex exec resume <SESSION_ID>
      --json -m MODEL ... "<PROMPT>"``. The session id is positional
      after ``resume``.

    The ``system_append`` block is prepended to ``prompt`` rather than
    passed as a flag — codex has no ``--append-system-prompt`` analogue.

    ``interactive=True`` is reserved for a future ``codex`` (no
    ``exec``) path; not used in headless tripwire spawns. Asserts the
    inputs match the resume/prompt invariants.
    """
    if interactive and prompt is not None:
        raise ValueError("prompt must be None when interactive=True")
    if not interactive and prompt is None:
        raise ValueError("prompt is required when interactive=False")

    cfg = defaults.config
    inv = defaults.invocation

    # Codex has no `--append-system-prompt` — fold it into the prompt.
    # Empty system_append is a common case (tests, sessions that don't
    # need system instructions); skip the marker block in that case.
    final_prompt: str | None = prompt
    if prompt is not None and system_append.strip():
        final_prompt = f"{system_append}\n\n---\n\n{prompt}"

    args: list[str] = [inv.command if inv.command != "claude" else "codex", "exec"]
    if resume:
        args += ["resume", codex_session_id]

    args += ["--json"]
    args += ["-m", cfg.model]
    # `-c key="value"` is the codex pattern for config overrides.
    # The value is parsed as TOML; quoting the string literal is safest.
    args += ["-c", f'model_reasoning_effort="{cfg.effort}"']
    args += ["--sandbox", inv.codex_sandbox]

    if final_prompt is not None:
        args.append(final_prompt)

    return args
