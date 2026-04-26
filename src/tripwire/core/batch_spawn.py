"""Batch session spawn with prompt-cache priming (KUI-96 §E3).

PMs frequently launch N parallel sessions in one go. They share a
substantial prefix — the project's ``CLAUDE.md`` plus shipped skills
plus on-disk project state — so a single priming claude call ahead
of the batch hydrates the prompt cache, and every subsequent spawn
reads from it on its first message.

The 2026-04-25 batch burned 224M cache_read tokens against the same
shared prefix; even a 30% reduction is ~$100/batch saved.

Public surface:

    batch_spawn(project_dir, session_ids, *, prime=True,
                prime_runner=..., spawn_runner=...,
                shared_system_content=None) -> BatchSpawnReport

The runners are dependency-injected so the orchestration logic
(priming order, batch-of-1 short-circuit, fallback when priming
fails) is unit-testable without shelling out to ``claude`` or
running real prep.

Cache TTL ceiling — investigation summary (full version in
``decisions.md`` §E3):

  Avenue 1: ``claude --help`` (v2.1.119) has no ``--cache-ttl``-
  style flag. ``--betas extended-cache-ttl-2025-04-11`` is rejected
  for OAuth/Max users with "Custom betas are only available for API
  key users. Ignoring provided betas." Even under API-key auth, the
  CLI emits ``cache_control: {type: "ephemeral"}`` with no explicit
  ``ttl`` — interpreted as 5 min by the API. Header alone does not
  change behaviour.

  Avenue 2: ``--settings '{cache: {ttl: 1h}}'`` is silently ignored
  (the settings schema has no cache-TTL key).

  Avenue 3: An SDK direct-call wrapper for the prime is feasible
  but doesn't help — the prompt cache is keyed on the request's
  system-prefix bytes, and ``claude -p`` prepends the proprietary
  Claude Code default system prompt that we cannot replicate from
  the SDK. SDK-primed cache entries are never read by subsequent
  ``claude -p`` spawns. Both prime AND spawn would need to bypass
  ``claude -p`` to fix this, which is out of scope for KUI-96.

  Conclusion: 5 min is the ceiling for the ``claude -p`` runtime.
  Tightly-spaced batches (within 5 min of prime) hit warm cache;
  staggered launches re-pay cache-creation cost — no worse than
  the pre-E3 baseline.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BatchSpawnReport:
    """Outcome of a batch-spawn invocation."""

    primed: bool = False
    spawned: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


# ---------- Priming runner ------------------------------------------------


def default_prime_runner(project_dir: Path, system_content: str) -> bool:
    """Send one no-op ``claude -p`` call carrying the shared system prompt.

    Returns True if the priming call exited cleanly. The call is best-
    effort: failures are logged and the batch proceeds without warm
    cache. We pass an empty user prompt and ``--max-turns 1`` so the
    call returns immediately after producing the cache entry.
    """
    if not shutil.which("claude"):
        logger.warning("batch_spawn: claude CLI not on PATH; skipping prime")
        return False
    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                "ok",
                "--max-turns",
                "1",
                "--append-system-prompt",
                system_content,
                "--output-format",
                "stream-json",
            ],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("batch_spawn: prime call failed: %s", exc)
        return False
    return result.returncode == 0


def default_spawn_runner(project_dir: Path, session_id: str) -> None:
    """Invoke ``tripwire session spawn <session_id>`` as a subprocess.

    The default runner shells out so the existing CLI gates
    (status, strict-check, prep, monitor fork) all run unchanged for
    each session. Tests inject a no-op runner.
    """
    cmd = [
        "tripwire",
        "session",
        "spawn",
        session_id,
        "--project-dir",
        str(project_dir),
    ]
    subprocess.run(cmd, check=True)


# ---------- Shared content resolution -------------------------------------


def _read_default_shared_content(project_dir: Path) -> str:
    """Read the project's CLAUDE.md as the default shared system prompt.

    Falls back to a tiny placeholder if the file is missing — the
    priming call still runs (which is also fine; the spawns produce
    full system content on their own and just won't get a cache hit
    for *this* placeholder).
    """
    claude_md = project_dir / "CLAUDE.md"
    if claude_md.is_file():
        return claude_md.read_text(encoding="utf-8")
    return "# project (no CLAUDE.md)\n"


# ---------- Orchestration -------------------------------------------------


def batch_spawn(
    project_dir: Path,
    session_ids: list[str],
    *,
    prime: bool = True,
    prime_runner: Callable[[Path, str], bool] = default_prime_runner,
    spawn_runner: Callable[[Path, str], None] = default_spawn_runner,
    shared_system_content: str | None = None,
) -> BatchSpawnReport:
    """Optionally prime the prompt cache, then spawn each session.

    A batch of 0 or 1 skips priming — the no-op call isn't free, and
    a single session has no sibling to share the cache with.
    """
    report = BatchSpawnReport()
    if not session_ids:
        return report

    if prime and len(session_ids) > 1:
        content = (
            shared_system_content
            if shared_system_content is not None
            else _read_default_shared_content(project_dir)
        )
        report.primed = bool(prime_runner(project_dir, content))

    for sid in session_ids:
        try:
            spawn_runner(project_dir, sid)
            report.spawned.append(sid)
        except subprocess.CalledProcessError as exc:
            report.failed.append((sid, f"spawn returned {exc.returncode}"))
        except (OSError, RuntimeError) as exc:
            report.failed.append((sid, str(exc)))

    return report


__all__ = [
    "BatchSpawnReport",
    "batch_spawn",
    "default_prime_runner",
    "default_spawn_runner",
]
