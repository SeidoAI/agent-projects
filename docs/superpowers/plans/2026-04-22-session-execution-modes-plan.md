# Session Execution Modes + Dual-PR Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `tripwire session spawn`'s `claude -p` subprocess launcher with a pluggable runtime model (tmux for live-attach, manual for prep-only), add a `tripwire session attach` subcommand, and extend `tripwire session complete` to open one PR per worktree with cross-linking.

**Architecture:** Three layers on top of the existing `spawn_config` resolution chain: (1) a runtime-agnostic **prep pipeline** (worktrees → skill copy → CLAUDE.md render → kickoff.md render), (2) a **runtime dispatcher** that reads `spawn_config.invocation.runtime` and looks up a `SessionRuntime` implementation, (3) two concrete runtimes — `TmuxRuntime` (live-attach) and `ManualRuntime` (prep-only). A new `run_pr_flow` step in `session_complete` iterates `runtime_state.worktrees` and emits one PR per repo.

**Tech Stack:** Python 3.12, pydantic v2, Click, pytest + Click's CliRunner, Jinja2 (for CLAUDE.md template), `subprocess` for tmux, `gh` CLI for PR creation, `importlib.resources` for package data access.

**Spec:** `docs/superpowers/specs/2026-04-22-session-execution-modes.md`

---

## File structure

### Created

| Path | Responsibility |
|---|---|
| `src/tripwire/runtimes/__init__.py` | `RUNTIMES` registry + re-exports |
| `src/tripwire/runtimes/base.py` | `SessionRuntime` protocol, `PreppedSession`, `AttachCommand` discriminated union |
| `src/tripwire/runtimes/manual.py` | `ManualRuntime` — prep-only; prints command |
| `src/tripwire/runtimes/tmux.py` | `TmuxRuntime` — tmux-managed interactive claude |
| `src/tripwire/runtimes/prep.py` | `prep.run()` orchestrator + helpers (`resolve_worktrees`, `copy_skills`, `render_claude_md`, `render_kickoff`) |
| `src/tripwire/templates/worktree/CLAUDE.md.j2` | Per-session CLAUDE.md template |
| `src/tripwire/core/session_pr_flow.py` | `run_pr_flow()` — dual-PR orchestration |
| `tests/unit/test_runtimes_manual.py` | ManualRuntime unit tests |
| `tests/unit/test_runtimes_tmux.py` | TmuxRuntime unit tests with a fake-tmux shim |
| `tests/unit/test_runtimes_prep.py` | prep pipeline unit tests |
| `tests/unit/test_runtimes_registry.py` | dispatcher / registry lookup tests |
| `tests/unit/test_build_claude_args_interactive.py` | interactive-mode argv tests |
| `tests/unit/test_session_attach_cli.py` | `tripwire session attach` CLI tests |
| `tests/unit/test_session_pr_flow.py` | dual-PR flow unit tests with a fake-gh shim |
| `tests/integration/test_session_execution_end_to_end.py` | end-to-end with real tmux (gated) |
| `tests/fixtures/fake_tmux.py` | tmux CLI shim for unit tests |
| `tests/fixtures/fake_gh.py` | gh CLI shim for unit tests |

### Modified

| Path | Change |
|---|---|
| `src/tripwire/models/spawn.py` | `SpawnInvocation.runtime: Literal["tmux", "manual"]` |
| `src/tripwire/models/session.py` | `AgentSession.merge_policy`, `AgentSession.commit_on_complete`; `RuntimeState.tmux_session_name` |
| `src/tripwire/core/spawn_config.py` | `build_claude_args` gains `interactive: bool = False` |
| `src/tripwire/templates/spawn/defaults.yaml` | `invocation.runtime: tmux` |
| `src/tripwire/cli/session.py` | `spawn` refactored to use prep + dispatch; new `attach` subcommand; `pause`/`abandon` dispatch via runtime |
| `src/tripwire/core/session_complete.py` | invokes `run_pr_flow()` after gate checks |

---

## Task sequencing

Phases in order: schema → runtime protocol + manual → tmux → CLI rewire → dual-PR. Each phase ends with a green test suite and a commit.

---

### Task 1: Add `runtime` field to `SpawnInvocation` + shipped default

**Files:**
- Modify: `src/tripwire/models/spawn.py`
- Modify: `src/tripwire/templates/spawn/defaults.yaml`
- Test: `tests/unit/test_spawn_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_spawn_config.py`:

```python
def test_runtime_defaults_to_tmux(tmp_path_project):
    from tripwire.core.spawn_config import load_resolved_spawn_config

    resolved = load_resolved_spawn_config(tmp_path_project)
    assert resolved.invocation.runtime == "tmux"


def test_runtime_session_override_beats_default(
    tmp_path_project, save_test_session
):
    from tripwire.core.spawn_config import load_resolved_spawn_config

    save_test_session(
        tmp_path_project,
        "s1",
        status="planned",
        spawn_config={"invocation": {"runtime": "manual"}},
    )
    from tripwire.core.session_store import load_session

    session = load_session(tmp_path_project, "s1")
    resolved = load_resolved_spawn_config(tmp_path_project, session=session)
    assert resolved.invocation.runtime == "manual"


def test_runtime_rejects_unknown_value(tmp_path_project, save_test_session):
    import pytest
    from pydantic import ValidationError

    from tripwire.core.spawn_config import load_resolved_spawn_config

    save_test_session(
        tmp_path_project,
        "s1",
        status="planned",
        spawn_config={"invocation": {"runtime": "docker"}},
    )
    from tripwire.core.session_store import load_session

    session = load_session(tmp_path_project, "s1")
    with pytest.raises(ValidationError):
        load_resolved_spawn_config(tmp_path_project, session=session)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/maia/Code/seido/projects/tripwire
uv run python -m pytest tests/unit/test_spawn_config.py -k runtime -v
```

Expected: three FAILs. Error: `SpawnInvocation` has no `runtime` field.

- [ ] **Step 3: Add the field to the model**

Replace the `SpawnInvocation` class in `src/tripwire/models/spawn.py`:

```python
from typing import Literal


class SpawnInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = "claude"
    runtime: Literal["tmux", "manual"] = "tmux"
    background: bool = True
    log_path_template: str = (
        "~/.tripwire/logs/{project_slug}/{session_id}-{timestamp}.log"
    )
```

- [ ] **Step 4: Update shipped defaults.yaml**

Add `runtime: tmux` under `invocation:` in `src/tripwire/templates/spawn/defaults.yaml`:

```yaml
invocation:
  command: claude
  runtime: tmux
  background: true
  log_path_template: "~/.tripwire/logs/{project_slug}/{session_id}-{timestamp}.log"
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_spawn_config.py -k runtime -v
```

Expected: three PASS.

- [ ] **Step 6: Full test suite green**

```bash
uv run python -m pytest tests/ -q
```

Expected: all pre-existing tests still pass (the `SpawnInvocation` extra-forbid may catch stale fixtures; fix any that surface).

- [ ] **Step 7: Commit**

```bash
git add src/tripwire/models/spawn.py src/tripwire/templates/spawn/defaults.yaml \
        tests/unit/test_spawn_config.py
git commit -m "feat(spawn): add invocation.runtime field (tmux|manual)"
```

---

### Task 2: Add `merge_policy` and `commit_on_complete` to `AgentSession`

**Files:**
- Modify: `src/tripwire/models/session.py`
- Test: `tests/unit/test_session_store.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_session_store.py`:

```python
def test_session_merge_policy_defaults_await_review(
    tmp_path_project, save_test_session
):
    from tripwire.core.session_store import load_session

    save_test_session(tmp_path_project, "s1", status="planned")
    session = load_session(tmp_path_project, "s1")
    assert session.merge_policy == "await_review"
    assert session.commit_on_complete == "auto"


def test_session_merge_policy_rejects_unknown_value(
    tmp_path_project, save_test_session
):
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        save_test_session(
            tmp_path_project,
            "s1",
            status="planned",
            merge_policy="force_merge",
        )


def test_session_commit_on_complete_manual(tmp_path_project, save_test_session):
    from tripwire.core.session_store import load_session

    save_test_session(
        tmp_path_project,
        "s1",
        status="planned",
        commit_on_complete="manual",
    )
    session = load_session(tmp_path_project, "s1")
    assert session.commit_on_complete == "manual"


def test_engagement_pr_urls_roundtrip(tmp_path_project, save_test_session):
    """EngagementEntry gains a pr_urls list for PR persistence."""
    from datetime import datetime, timezone

    from tripwire.core.session_store import load_session
    from tripwire.models.session import EngagementEntry

    save_test_session(tmp_path_project, "s1", status="planned")
    session = load_session(tmp_path_project, "s1")
    session.engagements.append(
        EngagementEntry(
            started_at=datetime.now(tz=timezone.utc),
            trigger="initial_launch",
            pr_urls=["https://github.com/a/b/pull/1", "https://github.com/c/d/pull/2"],
        )
    )

    from tripwire.core.session_store import save_session

    save_session(tmp_path_project, session)
    reloaded = load_session(tmp_path_project, "s1")
    assert reloaded.engagements[0].pr_urls == [
        "https://github.com/a/b/pull/1",
        "https://github.com/c/d/pull/2",
    ]
```

Note: the `save_test_session` fixture may need to accept `merge_policy` / `commit_on_complete` kwargs. Check the fixture at `tests/conftest.py` and extend if needed.

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_session_store.py -k "merge_policy or commit_on_complete" -v
```

Expected: FAIL — fields don't exist on `AgentSession`.

- [ ] **Step 3: Add the fields to the model**

In `src/tripwire/models/session.py`, inside `class AgentSession`, after the existing `runtime_state` field, add:

```python
    merge_policy: Literal[
        "await_review",
        "auto_merge_on_green",
        "auto_merge_immediate",
    ] = "await_review"
    commit_on_complete: Literal["auto", "manual"] = "auto"
```

Add `from typing import Literal` to the imports if it's not already there.

Extend `EngagementEntry` with `pr_urls`:

```python
class EngagementEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    trigger: str
    context: str | None = None
    ended_at: datetime | None = None
    outcome: str | None = None
    pr_urls: list[str] = Field(default_factory=list)     # NEW
```

Also add a new optional field to `RuntimeState` for tmux:

```python
class RuntimeState(BaseModel):
    ...
    claude_session_id: str | None = None
    langgraph_thread_id: str | None = None
    workspace_volume: str | None = None
    worktrees: list[WorktreeEntry] = Field(default_factory=list)
    pid: int | None = None
    tmux_session_name: str | None = None        # NEW
    started_at: datetime | str | None = None
    log_path: str | None = None
```

- [ ] **Step 4: Update the fixture (if needed)**

If `save_test_session` in `tests/conftest.py` doesn't accept arbitrary kwargs, add them. If the fixture builds a dict, add `merge_policy` and `commit_on_complete` as pass-through fields.

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_session_store.py -k "merge_policy or commit_on_complete" -v
uv run python -m pytest tests/ -q
```

Expected: new tests PASS; full suite stays green.

- [ ] **Step 6: Commit**

```bash
git add src/tripwire/models/session.py tests/unit/test_session_store.py tests/conftest.py
git commit -m "feat(session): add merge_policy, commit_on_complete, runtime_state.tmux_session_name"
```

---

### Task 3: Add `interactive: bool` kwarg to `build_claude_args`

**Files:**
- Modify: `src/tripwire/core/spawn_config.py`
- Test: `tests/unit/test_build_claude_args_interactive.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_build_claude_args_interactive.py`:

```python
"""Tests for build_claude_args interactive mode."""

from tripwire.core.spawn_config import build_claude_args
from tripwire.models.spawn import SpawnDefaults


def _defaults() -> SpawnDefaults:
    return SpawnDefaults.model_validate({
        "prompt_template": "hi",
        "system_prompt_append": "sa",
    })


def test_interactive_true_omits_p_flag_and_prompt():
    args = build_claude_args(
        _defaults(),
        prompt=None,
        interactive=True,
        system_append="sa",
        session_id="s1",
        claude_session_id="uuid-1",
    )
    assert "-p" not in args
    assert "hi" not in args
    assert "--session-id" in args
    assert "uuid-1" in args


def test_interactive_false_includes_p_flag_and_prompt():
    args = build_claude_args(
        _defaults(),
        prompt="run this",
        interactive=False,
        system_append="sa",
        session_id="s1",
        claude_session_id="uuid-1",
    )
    assert "-p" in args
    assert "run this" in args


def test_interactive_true_with_non_none_prompt_raises():
    import pytest

    with pytest.raises(ValueError, match="prompt must be None when interactive"):
        build_claude_args(
            _defaults(),
            prompt="don't",
            interactive=True,
            system_append="sa",
            session_id="s1",
            claude_session_id="uuid-1",
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run python -m pytest tests/unit/test_build_claude_args_interactive.py -v
```

Expected: FAIL — `interactive` is not a parameter.

- [ ] **Step 3: Implement**

Modify `build_claude_args` in `src/tripwire/core/spawn_config.py`:

```python
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
    - ``session_id`` — tripwire's human-readable slug, passed as
      ``--name``.
    - ``claude_session_id`` — claude's internal UUID, passed as
      ``--session-id``.
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_build_claude_args_interactive.py -v
uv run python -m pytest tests/ -q
```

Expected: new tests PASS; full suite green. Any existing callers still work because `interactive` defaults to `False`.

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/spawn_config.py tests/unit/test_build_claude_args_interactive.py
git commit -m "feat(spawn-config): add interactive kwarg to build_claude_args"
```

---

### Task 4: `SessionRuntime` protocol, `AttachCommand` union, `PreppedSession` dataclass, empty registry

**Files:**
- Create: `src/tripwire/runtimes/__init__.py`
- Create: `src/tripwire/runtimes/base.py`
- Test: `tests/unit/test_runtimes_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_runtimes_registry.py`:

```python
"""Tests for the runtime registry."""

import pytest

from tripwire.runtimes import RUNTIMES, get_runtime


def test_registry_has_tmux_and_manual():
    assert "tmux" in RUNTIMES
    assert "manual" in RUNTIMES


def test_get_runtime_unknown_raises_with_valid_options():
    with pytest.raises(ValueError) as exc_info:
        get_runtime("docker")
    assert "docker" in str(exc_info.value)
    assert "tmux" in str(exc_info.value)
    assert "manual" in str(exc_info.value)


def test_attach_exec_and_attach_instruction_are_distinct_types():
    from tripwire.runtimes.base import AttachExec, AttachInstruction

    e = AttachExec(argv=["tmux", "attach"])
    i = AttachInstruction(message="run this yourself")
    assert e.argv == ["tmux", "attach"]
    assert i.message == "run this yourself"
    assert not isinstance(e, AttachInstruction)
    assert not isinstance(i, AttachExec)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_runtimes_registry.py -v
```

Expected: FAIL — `tripwire.runtimes` module doesn't exist.

- [ ] **Step 3: Create the protocol and types**

Create `src/tripwire/runtimes/base.py`:

```python
"""SessionRuntime protocol and shared types.

Each runtime implementation (tmux, manual, future: container) owns
the lifecycle for one session: start, pause, abandon, status, attach.
The prep pipeline runs before ``start`` and is runtime-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from tripwire.models.session import AgentSession, WorktreeEntry
from tripwire.models.spawn import SpawnDefaults


@dataclass
class PreppedSession:
    """Output of the prep pipeline, consumed by a runtime's ``start``."""

    session_id: str
    session: AgentSession
    project_dir: Path
    code_worktree: Path
    worktrees: list[WorktreeEntry]
    claude_session_id: str
    prompt: str
    system_append: str
    spawn_defaults: SpawnDefaults


@dataclass
class AttachExec:
    """Runtime wants `tripwire session attach` to execvp this argv."""

    argv: list[str]


@dataclass
class AttachInstruction:
    """Runtime has no process to attach to; print this message instead."""

    message: str


AttachCommand = AttachExec | AttachInstruction


RuntimeStatus = Literal["running", "exited", "unknown"]


class SessionRuntime(Protocol):
    """Protocol for session execution runtimes."""

    name: str

    def validate_environment(self) -> None:
        """Raise click.ClickException (or similar) with a user-facing
        message if this runtime can't run on this host (e.g. tmux
        missing). Called at prep time BEFORE any filesystem mutation."""
        ...

    def start(self, prepped: PreppedSession) -> "RuntimeStartResult":
        """Launch the agent process. Returns state to persist on
        ``session.runtime_state``."""
        ...

    def pause(self, session: AgentSession) -> None: ...
    def abandon(self, session: AgentSession) -> None: ...
    def status(self, session: AgentSession) -> RuntimeStatus: ...
    def attach_command(self, session: AgentSession) -> AttachCommand: ...


@dataclass
class RuntimeStartResult:
    """What a runtime's ``start`` returns — fields the caller writes
    back onto ``session.runtime_state``."""

    claude_session_id: str
    worktrees: list[WorktreeEntry]
    started_at: str                  # ISO 8601
    tmux_session_name: str | None = None
    pid: int | None = None
    log_path: str | None = None
```

Create `src/tripwire/runtimes/__init__.py`:

```python
"""Session runtime registry.

``RUNTIMES`` maps runtime name → ``SessionRuntime`` instance. Resolved
at spawn time from ``spawn_config.invocation.runtime``.
"""

from __future__ import annotations

from tripwire.runtimes.base import (
    AttachCommand,
    AttachExec,
    AttachInstruction,
    PreppedSession,
    RuntimeStartResult,
    RuntimeStatus,
    SessionRuntime,
)
from tripwire.runtimes.manual import ManualRuntime
from tripwire.runtimes.tmux import TmuxRuntime

RUNTIMES: dict[str, SessionRuntime] = {
    "tmux": TmuxRuntime(),
    "manual": ManualRuntime(),
}


def get_runtime(name: str) -> SessionRuntime:
    """Look up a runtime by name. Raises ValueError on unknown names
    with the valid options in the message."""
    if name not in RUNTIMES:
        valid = ", ".join(sorted(RUNTIMES))
        raise ValueError(
            f"Unknown runtime '{name}'. Valid runtimes: {valid}"
        )
    return RUNTIMES[name]


__all__ = [
    "RUNTIMES",
    "get_runtime",
    "SessionRuntime",
    "PreppedSession",
    "RuntimeStartResult",
    "RuntimeStatus",
    "AttachCommand",
    "AttachExec",
    "AttachInstruction",
]
```

Create empty placeholder files so the imports resolve (we fill these in Tasks 8 and 9):

```python
# src/tripwire/runtimes/manual.py
"""ManualRuntime — prep-only, prints the command for the human to run."""


class ManualRuntime:
    name = "manual"
```

```python
# src/tripwire/runtimes/tmux.py
"""TmuxRuntime — manages an interactive claude inside a tmux session."""


class TmuxRuntime:
    name = "tmux"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_runtimes_registry.py -v
```

Expected: three PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/runtimes/ tests/unit/test_runtimes_registry.py
git commit -m "feat(runtimes): protocol + registry scaffolding"
```

---

### Task 5: `prep.resolve_worktrees` — extract worktree creation from `session.py`

**Files:**
- Create: `src/tripwire/runtimes/prep.py`
- Test: `tests/unit/test_runtimes_prep.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_runtimes_prep.py`:

```python
"""Tests for the runtime prep pipeline."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tripwire.runtimes.prep import resolve_worktrees


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=t", "-c", "user.email=t@t",
            "commit", "--allow-empty", "-q", "-m", "init",
        ],
        cwd=path, check=True,
    )


class TestResolveWorktrees:
    def test_creates_one_worktree_per_repo(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        code_clone = tmp_path / "code-clone"
        code_clone.mkdir()
        _init_repo(code_clone)

        project_clone = tmp_path / "project-clone"
        project_clone.mkdir()
        _init_repo(project_clone)

        save_test_session(
            tmp_path_project,
            "s1",
            status="queued",
            repos=[
                {"repo": "SeidoAI/code", "base_branch": "main"},
                {"repo": "SeidoAI/project", "base_branch": "main"},
            ],
        )

        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        def fake_resolve(_resolved: Path, repo: str) -> Path:
            return code_clone if repo == "SeidoAI/code" else project_clone

        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            side_effect=fake_resolve,
        ):
            entries = resolve_worktrees(
                session=session,
                project_dir=tmp_path_project,
                branch="feat/s1",
                base_ref="main",
            )

        assert len(entries) == 2
        assert entries[0].repo == "SeidoAI/code"
        assert entries[1].repo == "SeidoAI/project"
        for entry in entries:
            assert Path(entry.worktree_path).is_dir()

    def test_first_repo_is_the_code_worktree(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        code_clone = tmp_path / "code-clone"
        code_clone.mkdir()
        _init_repo(code_clone)

        save_test_session(
            tmp_path_project,
            "s1",
            status="queued",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        )

        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            return_value=code_clone,
        ):
            entries = resolve_worktrees(
                session=session,
                project_dir=tmp_path_project,
                branch="feat/s1",
                base_ref="main",
            )

        assert entries[0].repo == "SeidoAI/code"

    def test_missing_clone_path_errors(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="queued",
            repos=[{"repo": "SeidoAI/missing", "base_branch": "main"}],
        )

        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="No local clone"):
                resolve_worktrees(
                    session=session,
                    project_dir=tmp_path_project,
                    branch="feat/s1",
                    base_ref="main",
                )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_runtimes_prep.py::TestResolveWorktrees -v
```

Expected: FAIL — `prep.resolve_worktrees` doesn't exist.

- [ ] **Step 3: Implement**

Create `src/tripwire/runtimes/prep.py`:

```python
"""Runtime-agnostic prep pipeline.

Runs once per spawn before the runtime's ``start``:
- resolve_worktrees: create git worktrees for every session.repos entry
- copy_skills: copy the agent's declared skills into <code-worktree>/.claude/skills
- render_claude_md: render CLAUDE.md from the template
- render_kickoff: write the kickoff prompt to <code-worktree>/.tripwire/kickoff.md
- run: the orchestrator that calls all of the above and returns PreppedSession
"""

from __future__ import annotations

from pathlib import Path

from tripwire.core.git_helpers import (
    branch_exists,
    worktree_add,
    worktree_path_for_session,
)
from tripwire.models.session import AgentSession, WorktreeEntry


def _resolve_clone_path(project_dir: Path, repo: str) -> Path | None:
    """Look up the local clone path for a repo slug.

    Extracted verbatim from the existing ``_resolve_clone_path`` in
    ``cli/session.py`` so prep can call it without importing from the
    CLI layer.
    """
    from tripwire.cli.session import _resolve_clone_path as _impl

    return _impl(project_dir, repo)


def resolve_worktrees(
    *,
    session: AgentSession,
    project_dir: Path,
    branch: str,
    base_ref: str,
) -> list[WorktreeEntry]:
    """Create one git worktree per session.repos entry.

    The first entry in ``session.repos`` is the code worktree — it's
    where CLAUDE.md and .claude/skills/ get written and where the
    agent cds into. Additional worktrees (typically the
    project-tracking repo) are referenced from CLAUDE.md by their
    absolute paths.

    Raises RuntimeError if any repo doesn't have a resolvable local
    clone or if the requested branch already exists in a clone.
    """
    entries: list[WorktreeEntry] = []
    for rb in session.repos:
        clone_path = _resolve_clone_path(project_dir, rb.repo)
        if clone_path is None:
            raise RuntimeError(
                f"No local clone for {rb.repo}. "
                f"Set local path in project.yaml repos."
            )
        wt_path = worktree_path_for_session(clone_path, session.id)
        if wt_path.exists():
            raise RuntimeError(
                f"Worktree path {wt_path} already exists. "
                f"Use 'tripwire session cleanup {session.id}' to remove it."
            )
        if branch_exists(clone_path, branch):
            raise RuntimeError(
                f"Branch '{branch}' already exists in {clone_path}. "
                f"Delete the branch or pick a different name."
            )
        worktree_add(clone_path, wt_path, branch, rb.base_branch or base_ref)
        entries.append(
            WorktreeEntry(
                repo=rb.repo,
                clone_path=str(clone_path),
                worktree_path=str(wt_path),
                branch=branch,
            )
        )
    return entries
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_runtimes_prep.py::TestResolveWorktrees -v
```

Expected: three PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/runtimes/prep.py tests/unit/test_runtimes_prep.py
git commit -m "feat(runtimes): prep.resolve_worktrees — multi-worktree creation"
```

---

### Task 6: `prep.copy_skills` + gitignore worktree-local

**Files:**
- Modify: `src/tripwire/runtimes/prep.py`
- Modify: `tests/unit/test_runtimes_prep.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_runtimes_prep.py`:

```python
class TestCopySkills:
    def test_copies_named_skills_into_claude_skills(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git").mkdir()
        (worktree / ".git" / "info").mkdir()
        (worktree / ".git" / "info" / "exclude").touch()

        copy_skills(
            worktree=worktree,
            skill_names=["backend-development"],
        )

        skill_md = worktree / ".claude" / "skills" / "backend-development" / "SKILL.md"
        assert skill_md.is_file()
        assert "backend-development" in skill_md.read_text().lower()

    def test_copies_multiple_skills(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()

        copy_skills(
            worktree=worktree,
            skill_names=["backend-development", "verification"],
        )

        assert (worktree / ".claude/skills/backend-development/SKILL.md").is_file()
        assert (worktree / ".claude/skills/verification/SKILL.md").is_file()

    def test_missing_skill_raises(self, tmp_path):
        import pytest

        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()

        with pytest.raises(RuntimeError, match="no-such-skill"):
            copy_skills(
                worktree=worktree,
                skill_names=["no-such-skill"],
            )

    def test_existing_skills_dir_backed_up(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()
        existing = worktree / ".claude" / "skills"
        existing.mkdir(parents=True)
        (existing / "marker.txt").write_text("old")

        copy_skills(
            worktree=worktree,
            skill_names=["backend-development"],
        )

        # Old content moved to a backup sibling
        backups = list(worktree.glob(".claude/skills.bak.*"))
        assert len(backups) == 1
        assert (backups[0] / "marker.txt").read_text() == "old"
        # New skill is in place
        assert (
            worktree / ".claude/skills/backend-development/SKILL.md"
        ).is_file()

    def test_appends_to_git_info_exclude(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").write_text("# existing\n")

        copy_skills(
            worktree=worktree,
            skill_names=["backend-development"],
        )

        exclude = (worktree / ".git" / "info" / "exclude").read_text()
        assert ".claude/" in exclude
        assert ".tripwire/" in exclude
        assert "# existing" in exclude

    def test_git_info_exclude_idempotent(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()

        copy_skills(worktree=worktree, skill_names=["backend-development"])
        copy_skills(worktree=worktree, skill_names=["backend-development"])

        exclude = (worktree / ".git" / "info" / "exclude").read_text()
        assert exclude.count(".claude/") == 1
        assert exclude.count(".tripwire/") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_runtimes_prep.py::TestCopySkills -v
```

Expected: FAIL — `copy_skills` doesn't exist.

- [ ] **Step 3: Implement**

Append to `src/tripwire/runtimes/prep.py`:

```python
import shutil
from datetime import datetime, timezone
from importlib.resources import files


_MANAGED_EXCLUDES = (".claude/", ".tripwire/")


def copy_skills(*, worktree: Path, skill_names: list[str]) -> None:
    """Copy each named skill from tripwire.templates.skills into
    <worktree>/.claude/skills/<name>/. Back up any pre-existing
    .claude/skills/ directory, then append .claude/ and .tripwire/ to
    the worktree's .git/info/exclude (idempotent).
    """
    if not skill_names:
        # Still update git-info-exclude so .tripwire/ is ignored.
        _append_to_git_info_exclude(worktree)
        return

    source_root = files("tripwire.templates.skills")

    # Validate all skills exist before mutating anything.
    for name in skill_names:
        skill_src = source_root / name / "SKILL.md"
        if not skill_src.is_file():
            raise RuntimeError(
                f"Skill '{name}' not found in tripwire.templates.skills. "
                f"Check agents/<id>.yaml.context.skills."
            )

    dest_root = worktree / ".claude" / "skills"
    if dest_root.exists():
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = worktree / ".claude" / f"skills.bak.{ts}"
        dest_root.rename(backup)

    dest_root.mkdir(parents=True, exist_ok=True)
    for name in skill_names:
        src_dir = source_root / name
        dst_dir = dest_root / name
        # files() returns Traversable; use a recursive copy via
        # a temp directory to keep the logic simple.
        _copy_traversable(src_dir, dst_dir)

    _append_to_git_info_exclude(worktree)


def _copy_traversable(src, dst: Path) -> None:
    """Recursively copy an importlib.resources Traversable into dst."""
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        target = dst / entry.name
        if entry.is_dir():
            _copy_traversable(entry, target)
        else:
            target.write_bytes(entry.read_bytes())


def _append_to_git_info_exclude(worktree: Path) -> None:
    """Append .claude/ and .tripwire/ to the worktree's local gitignore
    (.git/info/exclude). Idempotent — existing entries are detected by
    line match."""
    exclude_path = worktree / ".git" / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.is_file() else ""
    lines = existing.splitlines()
    additions: list[str] = []
    for entry in _MANAGED_EXCLUDES:
        if entry not in lines:
            additions.append(entry)
    if additions:
        needs_trailing_nl = existing and not existing.endswith("\n")
        with exclude_path.open("a", encoding="utf-8") as fh:
            if needs_trailing_nl:
                fh.write("\n")
            for entry in additions:
                fh.write(entry + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_runtimes_prep.py::TestCopySkills -v
```

Expected: six PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/runtimes/prep.py tests/unit/test_runtimes_prep.py
git commit -m "feat(runtimes): prep.copy_skills — copy + backup + gitignore"
```

---

### Task 7: `prep.render_claude_md` + `prep.render_kickoff`

**Files:**
- Create: `src/tripwire/templates/worktree/CLAUDE.md.j2`
- Modify: `src/tripwire/runtimes/prep.py`
- Modify: `tests/unit/test_runtimes_prep.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_runtimes_prep.py`:

```python
class TestRenderClaudeMd:
    def test_renders_with_skill_and_worktree_refs(self, tmp_path):
        from tripwire.models.session import WorktreeEntry
        from tripwire.runtimes.prep import render_claude_md

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        project_wt = tmp_path / "project-wt"
        project_wt.mkdir()

        render_claude_md(
            code_worktree=code_wt,
            agent_id="backend-coder",
            skill_names=["backend-development"],
            worktrees=[
                WorktreeEntry(
                    repo="SeidoAI/code",
                    clone_path=str(tmp_path / "code-clone"),
                    worktree_path=str(code_wt),
                    branch="feat/s1",
                ),
                WorktreeEntry(
                    repo="SeidoAI/project-tracking",
                    clone_path=str(tmp_path / "project-clone"),
                    worktree_path=str(project_wt),
                    branch="feat/s1",
                ),
            ],
            session_id="s1",
        )

        out = (code_wt / "CLAUDE.md").read_text()
        assert "backend-coder" in out
        assert ".claude/skills/backend-development/SKILL.md" in out
        assert str(project_wt) in out
        assert "s1" in out

    def test_existing_claude_md_backed_up(self, tmp_path):
        from tripwire.runtimes.prep import render_claude_md

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        (code_wt / "CLAUDE.md").write_text("OLD")

        render_claude_md(
            code_worktree=code_wt,
            agent_id="backend-coder",
            skill_names=[],
            worktrees=[],
            session_id="s1",
        )

        backups = list(code_wt.glob("CLAUDE.md.bak.*"))
        assert len(backups) == 1
        assert backups[0].read_text() == "OLD"


class TestRenderKickoff:
    def test_writes_kickoff_md(self, tmp_path):
        from tripwire.runtimes.prep import render_kickoff

        code_wt = tmp_path / "wt"
        code_wt.mkdir()

        render_kickoff(code_worktree=code_wt, prompt="do the thing")

        kickoff = code_wt / ".tripwire" / "kickoff.md"
        assert kickoff.is_file()
        assert kickoff.read_text() == "do the thing"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_runtimes_prep.py::TestRenderClaudeMd tests/unit/test_runtimes_prep.py::TestRenderKickoff -v
```

Expected: FAIL — functions don't exist; template doesn't exist.

- [ ] **Step 3: Create the Jinja template**

Create `src/tripwire/templates/worktree/CLAUDE.md.j2`:

```markdown
# Agent: {{ agent_id }}

You are the `{{ agent_id }}` agent for session `{{ session_id }}`.

## Your skill{% if skill_names|length > 1 %}s{% endif %}

{% for skill in skill_names -%}
- [`{{ skill }}`](.claude/skills/{{ skill }}/SKILL.md) — read this first.
{% endfor %}

## Worktrees

Your work spans the following worktrees (all under tripwire management — `.claude/` and `.tripwire/` are gitignored here):

{% for wt in worktrees -%}
- **`{{ wt.repo }}`** — `{{ wt.worktree_path }}` (branch `{{ wt.branch }}`)
{% endfor %}

Your current working directory is the first worktree above. Session artifacts (plan.md, verification-checklist.md, issue specs, task-checklist.md) live in the **project-tracking worktree** — the second entry if present. Read and write them there directly; they will be committed and pushed as part of `tripwire session complete`.

## Session

- Session ID: `{{ session_id }}`
- Kickoff prompt: `.tripwire/kickoff.md` (also delivered as your first message)
```

- [ ] **Step 4: Implement the render functions**

Append to `src/tripwire/runtimes/prep.py`:

```python
from jinja2 import Environment, FileSystemLoader, select_autoescape
from tripwire.models.session import WorktreeEntry


def _template_env() -> Environment:
    import tripwire

    templates_root = Path(tripwire.__file__).parent / "templates" / "worktree"
    return Environment(
        loader=FileSystemLoader(str(templates_root)),
        autoescape=select_autoescape(disabled_extensions=("j2", "md")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_claude_md(
    *,
    code_worktree: Path,
    agent_id: str,
    skill_names: list[str],
    worktrees: list[WorktreeEntry],
    session_id: str,
) -> None:
    """Render <code_worktree>/CLAUDE.md from the template. Back up any
    existing CLAUDE.md first."""
    target = code_worktree / "CLAUDE.md"
    if target.exists():
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = code_worktree / f"CLAUDE.md.bak.{ts}"
        target.rename(backup)

    env = _template_env()
    tpl = env.get_template("CLAUDE.md.j2")
    out = tpl.render(
        agent_id=agent_id,
        skill_names=skill_names,
        worktrees=worktrees,
        session_id=session_id,
    )
    target.write_text(out, encoding="utf-8")


def render_kickoff(*, code_worktree: Path, prompt: str) -> None:
    """Write the kickoff prompt to <code-worktree>/.tripwire/kickoff.md.

    This file is what the operator pastes (manual mode) and what the
    tmux send-keys step delivers on ready-probe timeout."""
    kickoff = code_worktree / ".tripwire" / "kickoff.md"
    kickoff.parent.mkdir(parents=True, exist_ok=True)
    kickoff.write_text(prompt, encoding="utf-8")
```

Add `jinja2` to `pyproject.toml` dependencies if not already present. Check with:

```bash
uv run python -c "import jinja2; print(jinja2.__version__)"
```

If ImportError, add:

```toml
# In pyproject.toml under [project] dependencies
"jinja2>=3.1",
```

Then:

```bash
uv sync
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_runtimes_prep.py::TestRenderClaudeMd tests/unit/test_runtimes_prep.py::TestRenderKickoff -v
```

Expected: three PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tripwire/runtimes/prep.py \
        src/tripwire/templates/worktree/CLAUDE.md.j2 \
        tests/unit/test_runtimes_prep.py \
        pyproject.toml uv.lock
git commit -m "feat(runtimes): prep.render_claude_md + prep.render_kickoff"
```

---

### Task 8: `prep.run()` orchestrator

**Files:**
- Modify: `src/tripwire/runtimes/prep.py`
- Modify: `tests/unit/test_runtimes_prep.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_runtimes_prep.py`:

```python
class TestPrepRun:
    def test_end_to_end(
        self, tmp_path, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        import yaml as _yaml
        from unittest.mock import patch

        from tripwire.runtimes.prep import run as prep_run
        from tripwire.runtimes import RUNTIMES

        code_clone = tmp_path / "code-clone"
        code_clone.mkdir()
        _init_repo(code_clone)

        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        # Make sure the agent.yaml exists with a context.skills list
        agents_dir = tmp_path_project / "agents"
        agents_dir.mkdir(exist_ok=True)
        (agents_dir / "backend-coder.yaml").write_text(
            _yaml.safe_dump({
                "id": "backend-coder",
                "context": {"skills": ["backend-development"]},
            })
        )

        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            return_value=code_clone,
        ):
            prepped = prep_run(
                session=session,
                project_dir=tmp_path_project,
                runtime=RUNTIMES["manual"],
            )

        assert prepped.session_id == "s1"
        assert prepped.code_worktree.is_dir()
        assert (prepped.code_worktree / "CLAUDE.md").is_file()
        assert (
            prepped.code_worktree / ".claude/skills/backend-development/SKILL.md"
        ).is_file()
        assert (prepped.code_worktree / ".tripwire/kickoff.md").is_file()
        assert prepped.prompt  # non-empty
        assert prepped.claude_session_id
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run python -m pytest tests/unit/test_runtimes_prep.py::TestPrepRun -v
```

Expected: FAIL — `prep.run` doesn't exist.

- [ ] **Step 3: Implement**

Append to `src/tripwire/runtimes/prep.py`:

```python
import uuid as _uuid
import yaml as _yaml

from tripwire.core.handoff_store import load_handoff
from tripwire.core.paths import session_plan_path
from tripwire.core.spawn_config import (
    build_claude_args,
    load_resolved_spawn_config,
    render_prompt,
    render_system_append,
)
from tripwire.runtimes.base import PreppedSession, SessionRuntime


def run(
    *,
    session: AgentSession,
    project_dir: Path,
    runtime: SessionRuntime,
    max_turns_override: int | None = None,
    claude_session_id: str | None = None,
) -> PreppedSession:
    """Orchestrate all prep steps:

      1. validate_environment on the selected runtime
      2. resolve worktrees (one per session.repos)
      3. copy skills into <code-worktree>/.claude/skills/
      4. render CLAUDE.md
      5. render prompt + kickoff.md

    Returns a PreppedSession the runtime's ``start`` consumes.
    """
    runtime.validate_environment()

    handoff = load_handoff(project_dir, session.id)
    if handoff is None:
        raise RuntimeError(f"handoff.yaml not found for session '{session.id}'")
    branch = handoff.branch

    from tripwire.core.branch_naming import parse_branch_name

    try:
        branch_type, _ = parse_branch_name(branch)
    except Exception:
        branch_type = "feat"

    worktrees = resolve_worktrees(
        session=session,
        project_dir=project_dir,
        branch=branch,
        base_ref="HEAD",
    )
    if not worktrees:
        raise RuntimeError(f"session '{session.id}' has no repos configured")

    code_worktree = Path(worktrees[0].worktree_path)

    # Look up the agent's declared skills
    skill_names: list[str] = []
    agent_yaml = project_dir / "agents" / f"{session.agent}.yaml"
    if agent_yaml.is_file():
        try:
            agent_data = _yaml.safe_load(agent_yaml.read_text(encoding="utf-8")) or {}
            context = agent_data.get("context") or {}
            skills = context.get("skills") or []
            if isinstance(skills, list):
                skill_names = [str(s) for s in skills]
        except Exception:
            skill_names = []

    copy_skills(worktree=code_worktree, skill_names=skill_names)

    render_claude_md(
        code_worktree=code_worktree,
        agent_id=session.agent,
        skill_names=skill_names,
        worktrees=worktrees,
        session_id=session.id,
    )

    # Build the kickoff prompt
    plan_path = session_plan_path(project_dir, session.id)
    if not plan_path.is_file():
        raise RuntimeError(f"plan.md not found at {plan_path}")
    plan_content = plan_path.read_text(encoding="utf-8")

    resolved = load_resolved_spawn_config(project_dir, session=session)
    if max_turns_override is not None:
        resolved.config.max_turns = max_turns_override

    try:
        proj = _load_project_slug(project_dir)
    except Exception:
        proj = "unknown"

    prompt = render_prompt(
        resolved,
        plan=plan_content,
        agent=session.agent,
        session_id=session.id,
        session_name=session.name,
        branch_type=branch_type,
    )
    system_append = render_system_append(
        resolved,
        session_id=session.id,
        project_slug=proj,
    )

    render_kickoff(code_worktree=code_worktree, prompt=prompt)

    csid = claude_session_id or str(_uuid.uuid4())

    return PreppedSession(
        session_id=session.id,
        session=session,
        project_dir=project_dir,
        code_worktree=code_worktree,
        worktrees=worktrees,
        claude_session_id=csid,
        prompt=prompt,
        system_append=system_append,
        spawn_defaults=resolved,
    )


def _load_project_slug(project_dir: Path) -> str:
    from tripwire.core.store import load_project

    proj = load_project(project_dir)
    return proj.name.lower().replace(" ", "-")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run python -m pytest tests/unit/test_runtimes_prep.py::TestPrepRun -v
uv run python -m pytest tests/unit/test_runtimes_prep.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/runtimes/prep.py tests/unit/test_runtimes_prep.py
git commit -m "feat(runtimes): prep.run orchestrator — worktrees + skills + CLAUDE.md + kickoff"
```

---

### Task 9: `ManualRuntime` — full implementation

**Files:**
- Modify: `src/tripwire/runtimes/manual.py`
- Test: `tests/unit/test_runtimes_manual.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_runtimes_manual.py`:

```python
"""Tests for ManualRuntime."""

from pathlib import Path

from tripwire.models.session import AgentSession, RepoBinding, RuntimeState, WorktreeEntry
from tripwire.models.spawn import SpawnDefaults
from tripwire.runtimes import ManualRuntime
from tripwire.runtimes.base import AttachInstruction, PreppedSession


def _prepped(tmp_path) -> PreppedSession:
    wt = WorktreeEntry(
        repo="SeidoAI/code",
        clone_path=str(tmp_path / "clone"),
        worktree_path=str(tmp_path / "wt"),
        branch="feat/s1",
    )
    return PreppedSession(
        session_id="s1",
        session=AgentSession(id="s1", name="test", agent="a"),
        project_dir=tmp_path,
        code_worktree=tmp_path / "wt",
        worktrees=[wt],
        claude_session_id="uuid-1",
        prompt="do the thing",
        system_append="",
        spawn_defaults=SpawnDefaults(),
    )


def test_validate_environment_is_noop():
    ManualRuntime().validate_environment()  # does not raise


def test_start_prints_command_and_returns_state(tmp_path, capsys):
    runtime = ManualRuntime()
    prepped = _prepped(tmp_path)

    result = runtime.start(prepped)

    out = capsys.readouterr().out
    assert "claude --name s1 --session-id uuid-1" in out
    assert str(tmp_path / "wt") in out
    assert "kickoff.md" in out

    assert result.claude_session_id == "uuid-1"
    assert result.pid is None
    assert result.tmux_session_name is None


def test_pause_is_noop_but_warns(capsys):
    session = AgentSession(id="s1", name="t", agent="a")
    ManualRuntime().pause(session)
    out = capsys.readouterr().out
    assert "manual" in out.lower()


def test_abandon_is_noop_but_warns(capsys):
    session = AgentSession(id="s1", name="t", agent="a")
    ManualRuntime().abandon(session)
    out = capsys.readouterr().out
    assert "manual" in out.lower()


def test_status_is_unknown():
    session = AgentSession(id="s1", name="t", agent="a")
    assert ManualRuntime().status(session) == "unknown"


def test_attach_command_returns_instruction(tmp_path):
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(
            claude_session_id="uuid-1",
            worktrees=[
                WorktreeEntry(
                    repo="SeidoAI/code",
                    clone_path=str(tmp_path / "clone"),
                    worktree_path=str(tmp_path / "wt"),
                    branch="feat/s1",
                ),
            ],
        ),
    )
    cmd = ManualRuntime().attach_command(session)
    assert isinstance(cmd, AttachInstruction)
    assert "claude --name s1 --session-id uuid-1" in cmd.message
    assert str(tmp_path / "wt") in cmd.message
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_runtimes_manual.py -v
```

Expected: FAIL — methods not implemented.

- [ ] **Step 3: Implement**

Replace `src/tripwire/runtimes/manual.py`:

```python
"""ManualRuntime — prep-only runtime.

Does the skill copy + CLAUDE.md render like tmux, then prints the
exact claude invocation the operator should run, and exits. The
operator launches claude themselves from the code worktree.

Pause/abandon are no-ops (tripwire has no process handle); status is
always 'unknown'. Attach prints the same instruction as start.
"""

from __future__ import annotations

from datetime import datetime, timezone

import click

from tripwire.models.session import AgentSession
from tripwire.runtimes.base import (
    AttachCommand,
    AttachInstruction,
    PreppedSession,
    RuntimeStartResult,
    RuntimeStatus,
)


def _start_command(worktree: str, session_id: str, claude_session_id: str) -> str:
    return (
        f"cd {worktree}\n"
        f"  claude --name {session_id} --session-id {claude_session_id}"
    )


class ManualRuntime:
    name = "manual"

    def validate_environment(self) -> None:
        return

    def start(self, prepped: PreppedSession) -> RuntimeStartResult:
        click.echo("Prepared — manual runtime. To launch, run:")
        click.echo("")
        click.echo(
            "  " + _start_command(
                str(prepped.code_worktree),
                prepped.session_id,
                prepped.claude_session_id,
            )
        )
        click.echo("")
        click.echo(
            f"Kickoff prompt: {prepped.code_worktree}/.tripwire/kickoff.md "
            "(also loaded into claude on first turn via CLAUDE.md)."
        )
        return RuntimeStartResult(
            claude_session_id=prepped.claude_session_id,
            worktrees=prepped.worktrees,
            started_at=datetime.now(tz=timezone.utc).isoformat(),
        )

    def pause(self, session: AgentSession) -> None:
        click.echo(
            f"Session '{session.id}' is on the manual runtime — no process to pause. "
            "Interrupt claude yourself in the terminal where you launched it."
        )

    def abandon(self, session: AgentSession) -> None:
        click.echo(
            f"Session '{session.id}' is on the manual runtime — no process to abandon. "
            "Close the claude terminal yourself."
        )

    def status(self, session: AgentSession) -> RuntimeStatus:
        return "unknown"

    def attach_command(self, session: AgentSession) -> AttachCommand:
        state = session.runtime_state
        if not state.worktrees or not state.claude_session_id:
            return AttachInstruction(
                message=(
                    f"Session '{session.id}' has no recorded worktree or "
                    "claude session id. Re-run 'tripwire session spawn'."
                )
            )
        wt = state.worktrees[0].worktree_path
        return AttachInstruction(
            message=(
                "This session is on the manual runtime — launch it yourself:\n\n"
                f"  {_start_command(wt, session.id, state.claude_session_id)}\n"
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_runtimes_manual.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/runtimes/manual.py tests/unit/test_runtimes_manual.py
git commit -m "feat(runtimes): ManualRuntime — prep-only with instruction-based attach"
```

---

### Task 10: `TmuxRuntime` — `validate_environment` + `start` + ready-probe

**Files:**
- Create: `tests/fixtures/fake_tmux.py`
- Create: `tests/fixtures/conftest_fake_tmux.py` (pytest fixture)
- Modify: `src/tripwire/runtimes/tmux.py`
- Test: `tests/unit/test_runtimes_tmux.py`

- [ ] **Step 1: Build the fake-tmux fixture**

Create `tests/fixtures/fake_tmux.py` (a script the fixture will drop at a temp PATH location). This is a real executable that imitates tmux just enough for these tests. Python shebang so it's portable:

```python
#!/usr/bin/env python3
"""fake-tmux — records every invocation to a log file at $FAKE_TMUX_LOG.

Simulates tmux behaviours needed by TmuxRuntime unit tests:
- ``new-session -d -s NAME ...`` records the session name.
- ``capture-pane -pt NAME`` emits the contents of $FAKE_TMUX_PANE_TEXT.
- ``send-keys -t NAME ...`` records the keys.
- ``has-session -t NAME`` exits 0 if $FAKE_TMUX_HAS/<name> exists, 1 otherwise.
- ``kill-session -t NAME`` removes $FAKE_TMUX_HAS/<name>.
- ``attach -t NAME`` exits 0.
"""

import os
import sys
from pathlib import Path


def main() -> int:
    log_path = os.environ.get("FAKE_TMUX_LOG")
    if log_path:
        with open(log_path, "a") as fh:
            fh.write(" ".join(sys.argv[1:]) + "\n")

    args = sys.argv[1:]
    if not args:
        return 0

    cmd = args[0]
    has_dir = Path(os.environ.get("FAKE_TMUX_HAS", "/tmp/fake_tmux_has"))
    has_dir.mkdir(parents=True, exist_ok=True)

    if cmd == "new-session":
        # new-session -d -s NAME -c CWD -- claude ...
        if "-s" in args:
            name = args[args.index("-s") + 1]
            (has_dir / name).touch()
        return 0

    if cmd == "capture-pane":
        text = os.environ.get("FAKE_TMUX_PANE_TEXT", "")
        sys.stdout.write(text)
        return 0

    if cmd == "send-keys":
        return 0

    if cmd == "has-session":
        if "-t" in args:
            name = args[args.index("-t") + 1]
            return 0 if (has_dir / name).exists() else 1
        return 1

    if cmd == "kill-session":
        if "-t" in args:
            name = args[args.index("-t") + 1]
            (has_dir / name).unlink(missing_ok=True)
        return 0

    if cmd == "attach":
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Create `tests/conftest.py` additions (or a new file `tests/fixtures/conftest_fake_tmux.py` auto-loaded — but simpler: extend existing `tests/conftest.py`):

```python
# Add to tests/conftest.py (near top imports)
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def fake_tmux_on_path(tmp_path, monkeypatch):
    """Install a fake tmux executable on PATH and return a handle to
    inspect captured args, pane text, session-existence, etc."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    src = Path(__file__).parent / "fixtures" / "fake_tmux.py"
    dst = bin_dir / "tmux"
    shutil.copy(src, dst)
    dst.chmod(0o755)

    log_path = tmp_path / "fake_tmux.log"
    has_dir = tmp_path / "fake_tmux_has"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_TMUX_LOG", str(log_path))
    monkeypatch.setenv("FAKE_TMUX_HAS", str(has_dir))
    monkeypatch.setenv("FAKE_TMUX_PANE_TEXT", "")

    class Handle:
        def __init__(self):
            self.log_path = log_path
            self.has_dir = has_dir

        def calls(self) -> list[list[str]]:
            if not log_path.exists():
                return []
            return [
                line.split() for line in log_path.read_text().splitlines() if line
            ]

        def set_pane_text(self, text: str) -> None:
            monkeypatch.setenv("FAKE_TMUX_PANE_TEXT", text)

        def mark_session_exists(self, name: str) -> None:
            (has_dir / name).parent.mkdir(parents=True, exist_ok=True)
            (has_dir / name).touch()

    return Handle()
```

Add `import os` at the top of `tests/conftest.py` if not present.

- [ ] **Step 2: Write the failing tmux tests**

Create `tests/unit/test_runtimes_tmux.py`:

```python
"""Tests for TmuxRuntime."""

import os
from unittest.mock import patch

import pytest

from tripwire.models.session import AgentSession, WorktreeEntry
from tripwire.models.spawn import SpawnDefaults
from tripwire.runtimes.base import PreppedSession


def _prepped(tmp_path) -> PreppedSession:
    wt = WorktreeEntry(
        repo="SeidoAI/code",
        clone_path=str(tmp_path / "clone"),
        worktree_path=str(tmp_path / "wt"),
        branch="feat/s1",
    )
    (tmp_path / "wt").mkdir()
    return PreppedSession(
        session_id="s1",
        session=AgentSession(id="s1", name="test", agent="a"),
        project_dir=tmp_path,
        code_worktree=tmp_path / "wt",
        worktrees=[wt],
        claude_session_id="uuid-1",
        prompt="DO THE THING",
        system_append="",
        spawn_defaults=SpawnDefaults.model_validate({
            "prompt_template": "{plan}",
            "system_prompt_append": "",
        }),
    )


def test_validate_environment_missing_tmux_raises(monkeypatch):
    from tripwire.runtimes import TmuxRuntime

    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(Exception, match="tmux"):
        TmuxRuntime().validate_environment()


def test_validate_environment_with_tmux_present(fake_tmux_on_path):
    from tripwire.runtimes import TmuxRuntime

    TmuxRuntime().validate_environment()  # does not raise


def test_start_creates_tmux_session_and_sends_keys(fake_tmux_on_path, tmp_path):
    from tripwire.runtimes import TmuxRuntime

    prepped = _prepped(tmp_path)
    fake_tmux_on_path.set_pane_text("Welcome to claude\n> ")

    result = TmuxRuntime().start(prepped)

    calls = fake_tmux_on_path.calls()
    commands = [c[0] for c in calls]
    assert "new-session" in commands
    assert "send-keys" in commands

    new_session = next(c for c in calls if c[0] == "new-session")
    assert "-s" in new_session
    session_name = new_session[new_session.index("-s") + 1]
    assert session_name.startswith("tw-s1")

    send_keys = next(c for c in calls if c[0] == "send-keys")
    assert "DO THE THING" in " ".join(send_keys)
    assert "Enter" in send_keys

    assert result.tmux_session_name == session_name
    assert result.claude_session_id == "uuid-1"


def test_start_timeout_when_ready_prompt_never_appears(
    fake_tmux_on_path, tmp_path
):
    from tripwire.runtimes import TmuxRuntime

    prepped = _prepped(tmp_path)
    fake_tmux_on_path.set_pane_text("still starting...")  # never reaches "> "

    with patch("tripwire.runtimes.tmux._READY_POLL_INTERVAL", 0.01), \
         patch("tripwire.runtimes.tmux._READY_TIMEOUT", 0.05):
        with pytest.raises(Exception, match="did not reach ready prompt"):
            TmuxRuntime().start(prepped)

    # Session was still created
    calls = fake_tmux_on_path.calls()
    assert any(c[0] == "new-session" for c in calls)
    # send-keys was NOT called (we timed out before the prompt)
    assert not any(c[0] == "send-keys" for c in calls)
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_runtimes_tmux.py -v
```

Expected: FAIL — TmuxRuntime methods not implemented.

- [ ] **Step 4: Implement TmuxRuntime start**

Replace `src/tripwire/runtimes/tmux.py`:

```python
"""TmuxRuntime — manages an interactive claude inside a tmux session.

Uses tmux for the live-attach story. Launches
``claude --name <slug> --session-id <uuid>`` (no ``-p``) inside
``tmux new-session -d -s tw-<id>``, polls for claude's ready prompt
via ``tmux capture-pane``, then delivers the kickoff prompt with
``tmux send-keys``.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime, timezone

import click

from tripwire.core.spawn_config import build_claude_args
from tripwire.models.session import AgentSession
from tripwire.runtimes.base import (
    AttachCommand,
    AttachExec,
    AttachInstruction,
    PreppedSession,
    RuntimeStartResult,
    RuntimeStatus,
)

_READY_MARKER = "> "
_READY_POLL_INTERVAL = 0.25
_READY_TIMEOUT = 10.0


def _tmux_session_name(session_id: str) -> str:
    return f"tw-{session_id}"


def _wait_for_ready(session_name: str) -> None:
    """Poll `tmux capture-pane` until claude's ready prompt appears.
    Raises RuntimeError on timeout."""
    deadline = time.monotonic() + _READY_TIMEOUT
    while time.monotonic() < deadline:
        try:
            out = subprocess.run(
                ["tmux", "capture-pane", "-pt", session_name],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except subprocess.SubprocessError:
            out = None
        if out is not None and _READY_MARKER in out.stdout:
            return
        time.sleep(_READY_POLL_INTERVAL)
    raise RuntimeError(
        "claude did not reach ready prompt within "
        f"{int(_READY_TIMEOUT)}s. tmux session is still running — "
        f"attach with 'tripwire session attach <id>' and paste the "
        f"prompt from <code-worktree>/.tripwire/kickoff.md."
    )


class TmuxRuntime:
    name = "tmux"

    def validate_environment(self) -> None:
        if shutil.which("tmux") is None:
            raise click.ClickException(
                "tmux runtime requires tmux on PATH. "
                "Install tmux or set spawn_config.invocation.runtime: manual."
            )

    def start(self, prepped: PreppedSession) -> RuntimeStartResult:
        session_name = _tmux_session_name(prepped.session_id)
        claude_args = build_claude_args(
            prepped.spawn_defaults,
            prompt=None,
            interactive=True,
            system_append=prepped.system_append,
            session_id=prepped.session_id,
            claude_session_id=prepped.claude_session_id,
        )

        subprocess.run(
            [
                "tmux", "new-session", "-d",
                "-s", session_name,
                "-c", str(prepped.code_worktree),
                "--",
                *claude_args,
            ],
            check=True,
        )

        _wait_for_ready(session_name)

        subprocess.run(
            ["tmux", "send-keys", "-t", session_name, prepped.prompt, "Enter"],
            check=True,
        )

        return RuntimeStartResult(
            claude_session_id=prepped.claude_session_id,
            worktrees=prepped.worktrees,
            started_at=datetime.now(tz=timezone.utc).isoformat(),
            tmux_session_name=session_name,
        )

    # pause / abandon / status / attach_command — filled in Task 11
    def pause(self, session: AgentSession) -> None:
        raise NotImplementedError

    def abandon(self, session: AgentSession) -> None:
        raise NotImplementedError

    def status(self, session: AgentSession) -> RuntimeStatus:
        raise NotImplementedError

    def attach_command(self, session: AgentSession) -> AttachCommand:
        raise NotImplementedError
```

- [ ] **Step 5: Run tests to verify start passes**

```bash
uv run python -m pytest tests/unit/test_runtimes_tmux.py -v
```

Expected: `validate_environment` + `start` tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tripwire/runtimes/tmux.py \
        tests/fixtures/fake_tmux.py \
        tests/unit/test_runtimes_tmux.py \
        tests/conftest.py
git commit -m "feat(runtimes): TmuxRuntime — validate_environment + start + ready-probe"
```

---

### Task 11: `TmuxRuntime` — `pause`, `abandon`, `status`, `attach_command`

**Files:**
- Modify: `src/tripwire/runtimes/tmux.py`
- Modify: `tests/unit/test_runtimes_tmux.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_runtimes_tmux.py`:

```python
from tripwire.models.session import RuntimeState
from tripwire.runtimes.base import AttachExec


def _session_in_runtime(tmp_path, tmux_name: str = "tw-s1") -> AgentSession:
    return AgentSession(
        id="s1",
        name="test",
        agent="a",
        runtime_state=RuntimeState(
            claude_session_id="uuid-1",
            tmux_session_name=tmux_name,
            worktrees=[
                WorktreeEntry(
                    repo="SeidoAI/code",
                    clone_path=str(tmp_path / "clone"),
                    worktree_path=str(tmp_path / "wt"),
                    branch="feat/s1",
                ),
            ],
        ),
    )


def test_status_running_when_session_exists(fake_tmux_on_path, tmp_path):
    from tripwire.runtimes import TmuxRuntime

    fake_tmux_on_path.mark_session_exists("tw-s1")
    session = _session_in_runtime(tmp_path)

    assert TmuxRuntime().status(session) == "running"


def test_status_exited_when_session_absent(fake_tmux_on_path, tmp_path):
    from tripwire.runtimes import TmuxRuntime

    session = _session_in_runtime(tmp_path)

    assert TmuxRuntime().status(session) == "exited"


def test_pause_sends_ctrl_c(fake_tmux_on_path, tmp_path):
    from tripwire.runtimes import TmuxRuntime

    fake_tmux_on_path.mark_session_exists("tw-s1")
    session = _session_in_runtime(tmp_path)

    TmuxRuntime().pause(session)

    calls = fake_tmux_on_path.calls()
    send_keys = [c for c in calls if c[0] == "send-keys"]
    assert any("C-c" in c for c in send_keys)


def test_abandon_kills_session(fake_tmux_on_path, tmp_path):
    from tripwire.runtimes import TmuxRuntime

    fake_tmux_on_path.mark_session_exists("tw-s1")
    session = _session_in_runtime(tmp_path)

    TmuxRuntime().abandon(session)

    calls = fake_tmux_on_path.calls()
    assert any(c[0] == "kill-session" for c in calls)


def test_attach_command_returns_tmux_attach(fake_tmux_on_path, tmp_path):
    from tripwire.runtimes import TmuxRuntime

    session = _session_in_runtime(tmp_path)
    cmd = TmuxRuntime().attach_command(session)

    assert isinstance(cmd, AttachExec)
    assert cmd.argv[0] == "tmux"
    assert "attach" in cmd.argv
    assert "tw-s1" in cmd.argv


def test_attach_command_with_no_tmux_session_returns_instruction(tmp_path):
    from tripwire.runtimes import TmuxRuntime

    session = AgentSession(id="s1", name="t", agent="a")  # no runtime_state

    cmd = TmuxRuntime().attach_command(session)

    assert isinstance(cmd, AttachInstruction)
    assert "no tmux session" in cmd.message.lower() or "not found" in cmd.message.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_runtimes_tmux.py -v
```

Expected: new tests FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement**

Replace the placeholder methods in `src/tripwire/runtimes/tmux.py`:

```python
    def pause(self, session: AgentSession) -> None:
        name = session.runtime_state.tmux_session_name
        if not name:
            raise RuntimeError(
                f"Session '{session.id}' has no tmux_session_name in runtime_state."
            )
        subprocess.run(
            ["tmux", "send-keys", "-t", name, "C-c"],
            check=False,
        )

    def abandon(self, session: AgentSession) -> None:
        name = session.runtime_state.tmux_session_name
        if not name:
            return
        subprocess.run(
            ["tmux", "kill-session", "-t", name],
            check=False,
        )

    def status(self, session: AgentSession) -> RuntimeStatus:
        name = session.runtime_state.tmux_session_name
        if not name:
            return "unknown"
        rc = subprocess.run(
            ["tmux", "has-session", "-t", name],
            capture_output=True,
        ).returncode
        return "running" if rc == 0 else "exited"

    def attach_command(self, session: AgentSession) -> AttachCommand:
        name = session.runtime_state.tmux_session_name
        if not name:
            return AttachInstruction(
                message=(
                    f"Session '{session.id}' has no tmux session recorded. "
                    "The tmux session may not have been created, or "
                    "'tripwire session cleanup' has removed the runtime state."
                )
            )
        return AttachExec(argv=["tmux", "attach", "-t", name])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_runtimes_tmux.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/runtimes/tmux.py tests/unit/test_runtimes_tmux.py
git commit -m "feat(runtimes): TmuxRuntime lifecycle — pause/abandon/status/attach"
```

---

### Task 12: Refactor `session spawn` — dispatch through prep + runtime

**Files:**
- Modify: `src/tripwire/cli/session.py`
- Modify: `tests/unit/test_session_spawn_cli.py`

- [ ] **Step 1: Read the existing test set**

```bash
uv run python -m pytest tests/unit/test_session_spawn_cli.py -v
```

Make note of which tests currently pass. The refactor must keep all behavioural contracts intact: non-queued rejection, dry-run, claude-on-PATH check, session.status transitions to `executing`, worktree creation, engagement appended.

- [ ] **Step 2: Write failing tests for new behaviour**

Append to `tests/unit/test_session_spawn_cli.py`:

```python
class TestSpawnRuntimeDispatch:
    def test_spawn_uses_manual_runtime_when_configured(
        self,
        tmp_path,
        tmp_path_project,
        save_test_session,
        write_handoff_yaml,
    ):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[{"repo": "SeidoAI/tripwire", "base_branch": "main"}],
            spawn_config={"invocation": {"runtime": "manual"}},
        )
        write_handoff_yaml(tmp_path_project, "s1")

        # Fake agent.yaml
        (tmp_path_project / "agents").mkdir(exist_ok=True)
        (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
            "id: backend-coder\ncontext:\n  skills: []\n"
        )

        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch(
                 "tripwire.runtimes.prep._resolve_clone_path",
                 return_value=clone,
             ):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code == 0, result.output
        assert "manual" in result.output.lower()
        assert "claude --name s1" in result.output

        s = load_session(tmp_path_project, "s1")
        assert s.status == "executing"
        assert s.runtime_state.claude_session_id is not None
        assert len(s.runtime_state.worktrees) == 1
        # Worktree got the CLAUDE.md + kickoff.md
        wt = Path(s.runtime_state.worktrees[0].worktree_path)
        assert (wt / "CLAUDE.md").is_file()
        assert (wt / ".tripwire" / "kickoff.md").is_file()

    def test_spawn_uses_tmux_runtime_by_default(
        self,
        fake_tmux_on_path,
        tmp_path,
        tmp_path_project,
        save_test_session,
        write_handoff_yaml,
    ):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[{"repo": "SeidoAI/tripwire", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")
        (tmp_path_project / "agents").mkdir(exist_ok=True)
        (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
            "id: backend-coder\ncontext:\n  skills: []\n"
        )

        fake_tmux_on_path.set_pane_text("> ")

        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch(
                 "tripwire.runtimes.prep._resolve_clone_path",
                 return_value=clone,
             ):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.runtime_state.tmux_session_name == "tw-s1"
        assert s.runtime_state.pid is None

    def test_spawn_errors_when_tmux_missing_and_runtime_is_tmux(
        self,
        tmp_path,
        tmp_path_project,
        save_test_session,
        write_handoff_yaml,
        monkeypatch,
    ):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[{"repo": "SeidoAI/tripwire", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")
        (tmp_path_project / "agents").mkdir(exist_ok=True)
        (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
            "id: backend-coder\ncontext:\n  skills: []\n"
        )

        monkeypatch.setenv("PATH", "/nonexistent")

        with patch("shutil.which",
                   lambda x: "/usr/bin/claude" if x == "claude" else None), \
             patch(
                 "tripwire.runtimes.prep._resolve_clone_path",
                 return_value=clone,
             ):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code != 0
        assert "tmux" in result.output.lower()
        # Session still queued (prep errored before any state transition)
        s = load_session(tmp_path_project, "s1")
        assert s.status == "queued"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_session_spawn_cli.py::TestSpawnRuntimeDispatch -v
```

Expected: FAIL — spawn doesn't dispatch via runtime yet.

- [ ] **Step 4: Refactor the spawn command**

Replace the body of `session_spawn_cmd` in `src/tripwire/cli/session.py` (keep the decorator + options unchanged) with:

```python
def session_spawn_cmd(
    session_id: str,
    project_dir: Path,
    max_turns_override: int | None,
    log_dir: Path | None,
    dry_run: bool,
    resume_flag: bool,
) -> None:
    """Create worktree(s), dispatch to the configured runtime, transition to executing."""
    from tripwire.runtimes import get_runtime
    from tripwire.runtimes.prep import run as prep_run

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    # Status gate
    if resume_flag:
        if session.status not in ("failed", "paused"):
            raise click.ClickException(
                f"--resume requires status 'failed' or 'paused', got '{session.status}'"
            )
    else:
        if session.status != "queued":
            raise click.ClickException(
                f"session '{session_id}' is '{session.status}', must be 'queued' to spawn"
            )

    # Claude on PATH
    if not shutil.which("claude"):
        raise click.ClickException("claude CLI not found on PATH")

    # Resolve runtime
    from tripwire.core.spawn_config import load_resolved_spawn_config

    resolved_spawn = load_resolved_spawn_config(resolved, session=session)
    runtime = get_runtime(resolved_spawn.invocation.runtime)

    # Prep (runtime-agnostic: worktrees + skills + CLAUDE.md + kickoff)
    try:
        prepped = prep_run(
            session=session,
            project_dir=resolved,
            runtime=runtime,
            max_turns_override=max_turns_override,
            claude_session_id=(
                session.runtime_state.claude_session_id if resume_flag else None
            ),
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    if dry_run:
        click.echo(f"Dry run — would spawn session '{session_id}'")
        click.echo(f"  Runtime: {runtime.name}")
        for wt in prepped.worktrees:
            click.echo(f"  Worktree: {wt.worktree_path}")
        click.echo(f"  Max turns: {resolved_spawn.config.max_turns}")
        return

    # Launch via the runtime
    start_result = runtime.start(prepped)

    now = datetime.now(tz=timezone.utc)
    session.status = "executing"
    session.runtime_state.worktrees = start_result.worktrees
    session.runtime_state.claude_session_id = start_result.claude_session_id
    session.runtime_state.tmux_session_name = start_result.tmux_session_name
    session.runtime_state.pid = start_result.pid
    session.runtime_state.started_at = start_result.started_at
    session.runtime_state.log_path = start_result.log_path
    session.updated_at = now
    session.engagements.append(
        EngagementEntry(
            started_at=now,
            trigger="re_engagement" if resume_flag else "initial_launch",
        )
    )
    save_session(resolved, session)

    click.echo(f"Session '{session_id}' → executing  (runtime: {runtime.name})")
    click.echo(f"  Branch: {prepped.worktrees[0].branch}")
    click.echo(f"  Code worktree: {prepped.code_worktree}")
    if start_result.tmux_session_name:
        click.echo(f"  Tmux session: {start_result.tmux_session_name}")
        click.echo(f"\n  tripwire session attach {session_id}")
    if start_result.pid:
        click.echo(f"  PID: {start_result.pid}")
    click.echo(f"  Claude session: {start_result.claude_session_id}")
```

Also **delete** the `_launch_claude` helper (lines ~396–461 in the current file) — it's no longer used.

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_session_spawn_cli.py -v
```

Expected: new tests PASS and existing tests PASS (they may need minor adjustments for output format changes — e.g. "PID: …" is now conditional, and "Log: …" is gone).

If an existing test asserts on `runtime_state.pid`, update it to assert on `runtime_state.tmux_session_name` or `runtime_state.claude_session_id` depending on what's being exercised.

- [ ] **Step 6: Full regression run**

```bash
uv run python -m pytest tests/ -q
```

Expected: green.

- [ ] **Step 7: Commit**

```bash
git add src/tripwire/cli/session.py tests/unit/test_session_spawn_cli.py
git commit -m "feat(cli): session spawn dispatches through runtime registry"
```

---

### Task 13: New `tripwire session attach <id>` subcommand

**Files:**
- Modify: `src/tripwire/cli/session.py`
- Create: `tests/unit/test_session_attach_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_session_attach_cli.py`:

```python
"""Tests for tripwire session attach."""

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


class TestSessionAttach:
    def test_attach_manual_runtime_prints_instruction(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            spawn_config={"invocation": {"runtime": "manual"}},
            runtime_state={
                "claude_session_id": "uuid-1",
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": "/tmp/code",
                        "worktree_path": "/tmp/code-wt",
                        "branch": "feat/s1",
                    }
                ],
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["attach", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        assert "claude --name s1 --session-id uuid-1" in result.output

    def test_attach_tmux_runtime_execs_tmux(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            spawn_config={"invocation": {"runtime": "tmux"}},
            runtime_state={
                "claude_session_id": "uuid-1",
                "tmux_session_name": "tw-s1",
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": "/tmp/code",
                        "worktree_path": "/tmp/code-wt",
                        "branch": "feat/s1",
                    }
                ],
            },
        )

        with patch("os.execvp") as mock_execvp:
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["attach", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code == 0, result.output
        mock_execvp.assert_called_once()
        prog, argv = mock_execvp.call_args[0]
        assert prog == "tmux"
        assert "tw-s1" in argv

    def test_attach_session_not_found(self, tmp_path_project):
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["attach", "nope", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_attach_returns_instruction_when_tmux_name_missing(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            spawn_config={"invocation": {"runtime": "tmux"}},
            runtime_state={"claude_session_id": "uuid-1"},
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["attach", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        assert (
            "no tmux session" in result.output.lower()
            or "not found" in result.output.lower()
        )
```

If `save_test_session` doesn't accept `runtime_state` / `spawn_config` dict pass-throughs, extend the fixture in `tests/conftest.py` accordingly.

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_session_attach_cli.py -v
```

Expected: FAIL — `attach` subcommand doesn't exist.

- [ ] **Step 3: Implement**

Add to `src/tripwire/cli/session.py` (after the `session_spawn_cmd` function):

```python
@session_cmd.command("attach")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_attach_cmd(session_id: str, project_dir: Path) -> None:
    """Attach to a running session. Behaviour is runtime-specific:
    tmux runtimes exec `tmux attach`; manual runtimes print the
    command to run."""
    import os

    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime
    from tripwire.runtimes.base import AttachExec, AttachInstruction

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    spawn = load_resolved_spawn_config(resolved, session=session)
    runtime = get_runtime(spawn.invocation.runtime)
    cmd = runtime.attach_command(session)

    if isinstance(cmd, AttachExec):
        os.execvp(cmd.argv[0], cmd.argv)  # never returns
    elif isinstance(cmd, AttachInstruction):
        click.echo(cmd.message)
    else:
        raise click.ClickException(
            f"Runtime '{runtime.name}' returned unexpected attach command."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_session_attach_cli.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/cli/session.py tests/unit/test_session_attach_cli.py tests/conftest.py
git commit -m "feat(cli): new 'tripwire session attach' subcommand"
```

---

### Task 14: `session pause` / `session abandon` dispatch via runtime (with pid fallback)

**Files:**
- Modify: `src/tripwire/cli/session.py`
- Modify: `tests/unit/test_session_lifecycle_cli.py` (or nearest existing file)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_session_lifecycle_cli.py` (create file if not present, copying fixture patterns from `test_session_spawn_cli.py`):

```python
class TestSessionPauseDispatch:
    def test_pause_uses_runtime_abandon_for_tmux(
        self, fake_tmux_on_path, tmp_path_project, save_test_session
    ):
        fake_tmux_on_path.mark_session_exists("tw-s1")
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            spawn_config={"invocation": {"runtime": "tmux"}},
            runtime_state={
                "claude_session_id": "uuid-1",
                "tmux_session_name": "tw-s1",
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["pause", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        calls = fake_tmux_on_path.calls()
        assert any(c[0] == "send-keys" and "C-c" in c for c in calls)

        s = load_session(tmp_path_project, "s1")
        assert s.status == "paused"


class TestSessionAbandonDispatch:
    def test_abandon_uses_runtime_for_tmux(
        self, fake_tmux_on_path, tmp_path_project, save_test_session
    ):
        fake_tmux_on_path.mark_session_exists("tw-s1")
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            spawn_config={"invocation": {"runtime": "tmux"}},
            runtime_state={
                "claude_session_id": "uuid-1",
                "tmux_session_name": "tw-s1",
            },
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["abandon", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        calls = fake_tmux_on_path.calls()
        assert any(c[0] == "kill-session" for c in calls)

        s = load_session(tmp_path_project, "s1")
        assert s.status == "abandoned"


class TestSessionAbandonLegacyPidFallback:
    def test_abandon_v07_session_with_pid_only(
        self, tmp_path_project, save_test_session
    ):
        """v0.7 sessions have only pid — no tmux_session_name.
        Abandon should still fall through to SIGTERM path."""
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            runtime_state={"pid": 99999},  # non-existent pid
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["abandon", "s1", "--project-dir", str(tmp_path_project)],
        )

        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.status == "abandoned"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_session_lifecycle_cli.py -v
```

Expected: FAIL — pause/abandon still use only the pid path.

- [ ] **Step 3: Refactor pause + abandon**

Replace the body of `session_pause_cmd` in `src/tripwire/cli/session.py`:

```python
def session_pause_cmd(session_id: str, project_dir: Path) -> None:
    """Pause the session via its runtime, transition to paused."""
    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    if session.status != "executing":
        raise click.ClickException(
            f"session '{session_id}' is '{session.status}', must be 'executing' to pause"
        )

    now = datetime.now(tz=timezone.utc)

    # Runtime-driven pause
    spawn = load_resolved_spawn_config(resolved, session=session)
    runtime_name = spawn.invocation.runtime

    # v0.7 fallback: session has pid but no tmux_session_name — treat as
    # legacy subprocess and send SIGTERM directly.
    if runtime_name == "tmux" and not session.runtime_state.tmux_session_name:
        pid = session.runtime_state.pid
        if pid and is_alive(pid):
            send_sigterm(pid)
            session.status = "paused"
            click.echo(f"Session '{session_id}' → paused (legacy SIGTERM to PID {pid})")
        else:
            session.status = "failed"
            click.echo(f"Warning: PID {pid} not found — session '{session_id}' → failed")
    else:
        runtime = get_runtime(runtime_name)
        runtime.pause(session)
        session.status = "paused"
        click.echo(f"Session '{session_id}' → paused")

    session.updated_at = now
    save_session(resolved, session)
```

Replace the body of `session_abandon_cmd`:

```python
def session_abandon_cmd(session_id: str, project_dir: Path) -> None:
    """Kill the process/session via its runtime, transition to abandoned."""
    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    if session.status in ("completed", "abandoned"):
        raise click.ClickException(
            f"session '{session_id}' is already '{session.status}'"
        )

    spawn = load_resolved_spawn_config(resolved, session=session)
    runtime_name = spawn.invocation.runtime

    # v0.7 fallback
    if runtime_name == "tmux" and not session.runtime_state.tmux_session_name:
        pid = session.runtime_state.pid
        if pid and session.status == "executing" and is_alive(pid):
            send_sigterm(pid)
            click.echo(f"Sent SIGTERM to PID {pid}")
    else:
        runtime = get_runtime(runtime_name)
        if session.status == "executing":
            runtime.abandon(session)

    session.status = "abandoned"
    session.updated_at = datetime.now(tz=timezone.utc)
    save_session(resolved, session)
    click.echo(f"Session '{session_id}' → abandoned")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_session_lifecycle_cli.py -v
uv run python -m pytest tests/ -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/cli/session.py tests/unit/test_session_lifecycle_cli.py
git commit -m "feat(cli): session pause/abandon dispatch via runtime, keep pid fallback"
```

---

### Task 15: `run_pr_flow` — per-worktree commit + push + PR create (no cross-link yet)

**Files:**
- Create: `src/tripwire/core/session_pr_flow.py`
- Create: `tests/fixtures/fake_gh.py`
- Create: `tests/unit/test_session_pr_flow.py`

- [ ] **Step 1: Build the fake-gh fixture**

Create `tests/fixtures/fake_gh.py`:

```python
#!/usr/bin/env python3
"""fake-gh — stand-in for `gh` CLI in unit tests.

Records every invocation to $FAKE_GH_LOG, plus:
- ``pr create ... --repo R --head B ...`` emits a fake URL to stdout.
- ``pr list --repo R --head B --json url`` emits [] or [{"url": ...}]
  based on $FAKE_GH_EXISTING_PRS.
- ``pr edit ...`` succeeds silently.
- ``pr merge ...`` succeeds silently.
"""

import json
import os
import sys


def main() -> int:
    log = os.environ.get("FAKE_GH_LOG")
    if log:
        with open(log, "a") as fh:
            fh.write(" ".join(sys.argv[1:]) + "\n")

    args = sys.argv[1:]
    if args[:2] == ["pr", "create"]:
        # Fake URL derived from args
        repo = _flag(args, "--repo", default="unknown/repo")
        branch = _flag(args, "--head", default="unknown")
        sys.stdout.write(
            f"https://github.com/{repo}/pull/{abs(hash((repo, branch))) % 1000}\n"
        )
        return 0
    if args[:2] == ["pr", "list"]:
        existing = os.environ.get("FAKE_GH_EXISTING_PRS", "[]")
        sys.stdout.write(existing)
        return 0
    if args[:2] == ["pr", "edit"]:
        return 0
    if args[:2] == ["pr", "merge"]:
        return 0
    return 0


def _flag(args: list[str], name: str, default: str = "") -> str:
    if name in args:
        return args[args.index(name) + 1]
    return default


if __name__ == "__main__":
    sys.exit(main())
```

Add a fixture to `tests/conftest.py`:

```python
@pytest.fixture
def fake_gh_on_path(tmp_path, monkeypatch):
    bin_dir = tmp_path / "ghbin"
    bin_dir.mkdir()
    src = Path(__file__).parent / "fixtures" / "fake_gh.py"
    dst = bin_dir / "gh"
    shutil.copy(src, dst)
    dst.chmod(0o755)

    log_path = tmp_path / "fake_gh.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_LOG", str(log_path))

    class Handle:
        def calls(self) -> list[list[str]]:
            if not log_path.exists():
                return []
            return [line.split() for line in log_path.read_text().splitlines() if line]

        def set_existing_prs(self, urls: list[str]) -> None:
            items = [{"url": u} for u in urls]
            monkeypatch.setenv("FAKE_GH_EXISTING_PRS", json.dumps(items))

    return Handle()
```

Add `import json` at top of conftest if not present.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_session_pr_flow.py`:

```python
"""Tests for tripwire.core.session_pr_flow."""

import subprocess
from pathlib import Path

import pytest


def _init_repo_with_commit(path: Path, *, initial_branch: str = "main") -> None:
    subprocess.run(["git", "init", "-q", "-b", initial_branch], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit",
         "--allow-empty", "-q", "-m", "init"],
        cwd=path, check=True,
    )


def _add_commit_on_branch(wt: Path, branch: str, marker: str) -> None:
    subprocess.run(["git", "checkout", "-q", "-b", branch], cwd=wt, check=True)
    (wt / "marker.txt").write_text(marker)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "add", "marker.txt"],
        cwd=wt, check=True,
    )
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "-m", f"marker: {marker}"],
        cwd=wt, check=True,
    )


class TestRunPrFlowBasic:
    def test_opens_one_pr_per_dirty_worktree(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        # Two fake "worktrees" that are real git repos for the flow
        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "code-change")

        project_wt = tmp_path / "project-wt"
        project_wt.mkdir()
        _init_repo_with_commit(project_wt)
        _add_commit_on_branch(project_wt, "feat/s1", "project-change")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[
                {"repo": "SeidoAI/code", "base_branch": "main"},
                {"repo": "SeidoAI/project", "base_branch": "main"},
            ],
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    },
                    {
                        "repo": "SeidoAI/project",
                        "clone_path": str(project_wt),
                        "worktree_path": str(project_wt),
                        "branch": "feat/s1",
                    },
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")

        # Disable actual push; the test repos have no remote
        result = run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        pr_calls = [c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "create"]]
        assert len(pr_calls) == 2
        assert len(result.pr_urls) == 2
        for url in result.pr_urls:
            assert url.startswith("https://github.com/")

    def test_skips_repo_with_no_new_commits(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        # Only code worktree has a change; project is untouched
        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "code-change")

        project_wt = tmp_path / "project-wt"
        project_wt.mkdir()
        _init_repo_with_commit(project_wt)
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat/s1"], cwd=project_wt, check=True
        )
        # No commit on feat/s1 in project_wt

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[
                {"repo": "SeidoAI/code", "base_branch": "main"},
                {"repo": "SeidoAI/project", "base_branch": "main"},
            ],
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    },
                    {
                        "repo": "SeidoAI/project",
                        "clone_path": str(project_wt),
                        "worktree_path": str(project_wt),
                        "branch": "feat/s1",
                    },
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        result = run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        pr_calls = [c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "create"]]
        assert len(pr_calls) == 1
        assert len(result.pr_urls) == 1

    def test_auto_commits_dirty_worktree_when_policy_is_auto(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat/s1"], cwd=code_wt, check=True
        )
        # Uncommitted change on feat/s1
        (code_wt / "dirty.txt").write_text("uncommitted")
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "add", "dirty.txt"],
            cwd=code_wt, check=True,
        )

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            commit_on_complete="auto",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        result = run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )
        # Committed + PR created
        head_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=code_wt, capture_output=True, text=True, check=True,
        ).stdout
        assert "dirty" in head_log.lower() or len(head_log.splitlines()) >= 2
        assert len(result.pr_urls) == 1

    def test_commit_on_complete_manual_aborts_on_dirty(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import PrFlowError, run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat/s1"], cwd=code_wt, check=True
        )
        (code_wt / "dirty.txt").write_text("uncommitted")
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "add", "dirty.txt"],
            cwd=code_wt, check=True,
        )

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            commit_on_complete="manual",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")

        with pytest.raises(PrFlowError, match="uncommitted"):
            run_pr_flow(
                session=session,
                project_dir=tmp_path_project,
                skip_push=True,
            )
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_session_pr_flow.py -v
```

Expected: FAIL — `session_pr_flow` module doesn't exist.

- [ ] **Step 4: Implement `run_pr_flow` (without cross-link)**

Create `src/tripwire/core/session_pr_flow.py`:

```python
"""Dual-PR orchestration for tripwire session complete.

Iterates session.runtime_state.worktrees, commits+pushes when
appropriate, opens a PR per repo, cross-links the sibling PR URLs,
and applies the session's merge_policy. Partial-failure-safe:
re-running detects existing PRs on the same branch and skips to
cross-linking.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from tripwire.models.session import AgentSession


class PrFlowError(Exception):
    pass


@dataclass
class PrFlowResult:
    pr_urls: list[str] = field(default_factory=list)
    skipped_repos: list[str] = field(default_factory=list)
    committed_repos: list[str] = field(default_factory=list)


def _run_git(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def _is_dirty(worktree: Path) -> bool:
    r = _run_git(["status", "--porcelain"], cwd=worktree, check=False)
    return bool(r.stdout.strip())


def _branch_has_new_commits(worktree: Path, base: str) -> bool:
    r = _run_git(
        ["rev-list", "--count", f"{base}..HEAD"],
        cwd=worktree, check=False,
    )
    if r.returncode != 0:
        return False
    try:
        return int(r.stdout.strip()) > 0
    except ValueError:
        return False


def _find_existing_pr(repo: str, branch: str) -> str | None:
    r = subprocess.run(
        ["gh", "pr", "list", "--repo", repo, "--head", branch, "--json", "url"],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return None
    try:
        items = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not items:
        return None
    return items[0].get("url")


def _render_commit_message(session: AgentSession, repo: str) -> str:
    return (
        f"chore(tripwire): session {session.id} — {repo}\n\n"
        f"Automated commit by tripwire session complete."
    )


def _render_pr_title(session: AgentSession, repo: str) -> str:
    return f"feat({session.id}): {session.name} [{repo}]"


def _render_pr_body(session: AgentSession, repo: str, sibling_urls: list[str]) -> str:
    lines = [
        f"Session: `{session.id}`",
        f"Name: {session.name}",
        f"Issues: {', '.join(session.issues) or '—'}",
        "",
        "Automated by `tripwire session complete`.",
    ]
    if sibling_urls:
        lines += ["", "## Sibling PRs"]
        lines += [f"- {u}" for u in sibling_urls]
    return "\n".join(lines)


def run_pr_flow(
    *,
    session: AgentSession,
    project_dir: Path,
    skip_push: bool = False,
) -> PrFlowResult:
    """For each worktree with new commits vs base_branch, create or
    reuse a PR. Caller is responsible for invoking this only when
    session_complete's gates have passed.
    """
    result = PrFlowResult()

    # Map repo → base_branch (declared on session.repos) for base lookups
    base_branch_by_repo = {rb.repo: rb.base_branch for rb in session.repos}

    for wt in session.runtime_state.worktrees:
        wt_path = Path(wt.worktree_path)
        repo = wt.repo
        branch = wt.branch
        base = base_branch_by_repo.get(repo, "main")

        if _is_dirty(wt_path):
            if session.commit_on_complete == "auto":
                _run_git(["add", "-A"], cwd=wt_path)
                _run_git(
                    [
                        "-c", "user.name=tripwire",
                        "-c", "user.email=tripwire@local",
                        "commit", "-m", _render_commit_message(session, repo),
                    ],
                    cwd=wt_path,
                )
                result.committed_repos.append(repo)
            else:  # "manual"
                raise PrFlowError(
                    f"Worktree {wt_path} has uncommitted changes and "
                    f"session.commit_on_complete is 'manual'. "
                    f"Commit or discard, then rerun."
                )

        if not _branch_has_new_commits(wt_path, base):
            result.skipped_repos.append(repo)
            continue

        if not skip_push:
            _run_git(["push", "origin", branch], cwd=wt_path)

        existing_url = _find_existing_pr(repo, branch)
        if existing_url is None:
            pr_create = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--repo", repo,
                    "--base", base,
                    "--head", branch,
                    "--title", _render_pr_title(session, repo),
                    "--body", _render_pr_body(session, repo, sibling_urls=[]),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            url = (pr_create.stdout or "").strip().splitlines()[-1]
        else:
            url = existing_url

        result.pr_urls.append(url)

    return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_session_pr_flow.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tripwire/core/session_pr_flow.py \
        tests/fixtures/fake_gh.py \
        tests/unit/test_session_pr_flow.py \
        tests/conftest.py
git commit -m "feat(session-complete): run_pr_flow — per-worktree commit/push/PR (no cross-link)"
```

---

### Task 16: `run_pr_flow` — cross-link PR bodies + merge policy

**Files:**
- Modify: `src/tripwire/core/session_pr_flow.py`
- Modify: `tests/unit/test_session_pr_flow.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_session_pr_flow.py`:

```python
class TestRunPrFlowCrossLink:
    def test_pr_bodies_cross_link_when_two_prs_open(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "c")

        project_wt = tmp_path / "project-wt"
        project_wt.mkdir()
        _init_repo_with_commit(project_wt)
        _add_commit_on_branch(project_wt, "feat/s1", "p")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[
                {"repo": "SeidoAI/code", "base_branch": "main"},
                {"repo": "SeidoAI/project", "base_branch": "main"},
            ],
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    },
                    {
                        "repo": "SeidoAI/project",
                        "clone_path": str(project_wt),
                        "worktree_path": str(project_wt),
                        "branch": "feat/s1",
                    },
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        result = run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        edits = [c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "edit"]]
        # One edit per PR after second pass
        assert len(edits) == len(result.pr_urls) == 2

    def test_merge_policy_await_review_does_not_merge(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "c")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            merge_policy="await_review",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        merges = [c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "merge"]]
        assert merges == []

    def test_merge_policy_auto_on_green_passes_auto_flag(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "c")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            merge_policy="auto_merge_on_green",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        merges = [c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "merge"]]
        assert len(merges) == 1
        joined = " ".join(merges[0])
        assert "--auto" in joined
        assert "--squash" in joined

    def test_merge_policy_auto_immediate_omits_auto_flag(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "c")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            merge_policy="auto_merge_immediate",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        merges = [c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "merge"]]
        assert len(merges) == 1
        joined = " ".join(merges[0])
        assert "--auto" not in joined
        assert "--squash" in joined
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run python -m pytest tests/unit/test_session_pr_flow.py::TestRunPrFlowCrossLink -v
```

Expected: FAIL — no edit or merge calls are made yet.

- [ ] **Step 3: Extend `run_pr_flow`**

At the end of `run_pr_flow` in `src/tripwire/core/session_pr_flow.py`, before `return result`, add:

```python
    # Second pass: cross-link sibling URLs into each PR body
    if len(result.pr_urls) > 1:
        for i, url in enumerate(result.pr_urls):
            siblings = [u for j, u in enumerate(result.pr_urls) if j != i]
            # The PR's repo is the one we created/found it for; recover by
            # walking worktrees in the same order we pushed them (skipping
            # no-change repos)
            # Simpler: run edit with just --body using the stored URL
            new_body = _render_pr_body(
                session=session,
                repo="",  # repo name already in the title; body doesn't need it
                sibling_urls=siblings,
            )
            subprocess.run(
                ["gh", "pr", "edit", url, "--body", new_body],
                check=False,
            )

    # Merge policy
    policy = session.merge_policy
    if policy == "auto_merge_on_green":
        for url in result.pr_urls:
            subprocess.run(
                ["gh", "pr", "merge", "--auto", "--squash", url],
                check=False,
            )
    elif policy == "auto_merge_immediate":
        for url in result.pr_urls:
            subprocess.run(
                ["gh", "pr", "merge", "--squash", url],
                check=False,
            )
    # await_review: no-op

    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run python -m pytest tests/unit/test_session_pr_flow.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tripwire/core/session_pr_flow.py tests/unit/test_session_pr_flow.py
git commit -m "feat(session-complete): cross-link PR bodies + merge policy dispatch"
```

---

### Task 17: Wire `run_pr_flow` into `session_complete`

**Files:**
- Modify: `src/tripwire/core/session_complete.py`
- Modify: `tests/unit/test_session_complete.py`

- [ ] **Step 1: Read the current complete flow**

```bash
uv run python -m pytest tests/unit/test_session_complete.py -v
```

Note which tests pass. Read `src/tripwire/core/session_complete.py` fully to find the point where all gates have passed and the session is about to be marked `done`.

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_session_complete.py`:

```python
class TestCompleteInvokesPrFlow:
    def test_complete_runs_pr_flow_after_gates(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        """A happy-path complete should invoke run_pr_flow and record
        the resulting PR URLs in engagements."""
        from unittest.mock import patch

        from tripwire.core.session_complete import complete_session
        from tripwire.core.session_store import load_session

        # Build two real git worktrees with a commit each
        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=code_wt, check=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "--allow-empty", "-q", "-m", "init"],
            cwd=code_wt, check=True,
        )
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat/s1"], cwd=code_wt, check=True
        )
        (code_wt / "f.txt").write_text("x")
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "add", "f.txt"], cwd=code_wt, check=True,
        )
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "commit", "-q", "-m", "work"], cwd=code_wt, check=True,
        )

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )

        # Patch anything gate-related that tries to reach out: assume
        # session_complete has hooks for skip flags. If not, pass them
        # via the force=True shortcut.
        result = complete_session(
            tmp_path_project,
            "s1",
            dry_run=False,
            force=True,  # bypass gate checks — we're testing the pr_flow hook
            force_review=True,
            skip_artifact_check=True,
            skip_worktree_cleanup=True,
            skip_pr_merge_check=True,
        )

        pr_calls = [c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "create"]]
        assert len(pr_calls) == 1

        s = load_session(tmp_path_project, "s1")
        assert s.status == "completed"
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
uv run python -m pytest tests/unit/test_session_complete.py::TestCompleteInvokesPrFlow -v
```

Expected: FAIL — no PR calls observed.

- [ ] **Step 4: Wire it in**

In `src/tripwire/core/session_complete.py`, find the `complete_session` function. Just before the line that sets `session.status = "completed"` (or wherever the final status transition occurs), insert:

```python
    from tripwire.core.session_pr_flow import PrFlowError, run_pr_flow

    if not dry_run and not skip_pr_merge_check:
        try:
            pr_result = run_pr_flow(
                session=session,
                project_dir=project_dir,
                skip_push=False,
            )
        except PrFlowError as exc:
            raise CompleteError(
                code="PR_FLOW_FAILED",
                message=str(exc),
            )
        # Store PR URLs on the latest engagement for audit.
        if pr_result.pr_urls and session.engagements:
            session.engagements[-1].pr_urls = list(pr_result.pr_urls)
```

If `skip_pr_merge_check` is already being used for some other purpose in the existing `complete_session`, use a new flag `skip_pr_flow` instead, plumbed through `session_complete_cmd`. Adjust the command signature if needed.

- [ ] **Step 5: Run the test to verify it passes**

```bash
uv run python -m pytest tests/unit/test_session_complete.py -v
```

Expected: new test PASS; existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tripwire/core/session_complete.py tests/unit/test_session_complete.py
git commit -m "feat(session-complete): invoke run_pr_flow after gates"
```

---

### Task 18: End-to-end integration test (tmux-gated) + final cleanup

**Files:**
- Create: `tests/integration/test_session_execution_end_to_end.py`
- Modify: `src/tripwire/cli/session.py` (verify `_launch_claude` removed)

- [ ] **Step 1: Verify old code is removed**

Grep for the old Popen call:

```bash
grep -n "_launch_claude" src/tripwire/cli/session.py
```

Expected: no matches (should have been removed in Task 12). If it's still there, remove it now and re-run the suite.

- [ ] **Step 2: Write the integration test**

Create `tests/integration/test_session_execution_end_to_end.py`:

```python
"""End-to-end test for session execution modes.

Gated on tmux being installed. Exercises: session spawn in tmux mode
creates the tmux session with the right cwd, CLAUDE.md, skills, and
kickoff.md; session attach execvp's tmux; session abandon kills the
tmux session.
"""

import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session


pytestmark = pytest.mark.skipif(
    shutil.which("tmux") is None,
    reason="tmux not installed — integration test skipped",
)


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=path, check=True,
    )


@pytest.fixture
def fake_claude_on_path(tmp_path, monkeypatch):
    """A claude that just sleeps — lets tmux think the command is
    alive without actually launching claude."""
    bin_dir = tmp_path / "claudebin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text("#!/bin/sh\nexec sleep 60\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return fake


def test_tmux_mode_end_to_end(
    fake_claude_on_path,
    tmp_path,
    tmp_path_project,
    save_test_session,
    write_handoff_yaml,
):
    clone = tmp_path / "clone"
    clone.mkdir()
    _init_repo(clone)

    save_test_session(
        tmp_path_project,
        "s1",
        plan=True,
        status="queued",
        repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        spawn_config={"invocation": {"runtime": "tmux"}},
    )
    write_handoff_yaml(tmp_path_project, "s1")
    (tmp_path_project / "agents").mkdir(exist_ok=True)
    (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
        "id: backend-coder\ncontext:\n  skills: [backend-development]\n"
    )

    with patch(
        "tripwire.runtimes.prep._resolve_clone_path",
        return_value=clone,
    ):
        runner = CliRunner()
        # spawn
        spawn_result = runner.invoke(
            session_cmd,
            ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            catch_exceptions=False,
        )

    try:
        assert spawn_result.exit_code == 0, spawn_result.output
        session = load_session(tmp_path_project, "s1")
        assert session.runtime_state.tmux_session_name == "tw-s1"

        # tmux session exists
        has = subprocess.run(
            ["tmux", "has-session", "-t", "tw-s1"],
            capture_output=True,
        )
        assert has.returncode == 0

        # Worktree has the expected files
        wt = Path(session.runtime_state.worktrees[0].worktree_path)
        assert (wt / "CLAUDE.md").is_file()
        assert (wt / ".claude/skills/backend-development/SKILL.md").is_file()
        assert (wt / ".tripwire/kickoff.md").is_file()
        exclude = (wt / ".git/info/exclude").read_text()
        assert ".claude/" in exclude
        assert ".tripwire/" in exclude
    finally:
        # abandon (cleanup tmux)
        subprocess.run(["tmux", "kill-session", "-t", "tw-s1"], check=False)
```

- [ ] **Step 3: Run the integration test**

```bash
uv run python -m pytest tests/integration/test_session_execution_end_to_end.py -v
```

Expected: PASS if tmux is installed, SKIPPED otherwise.

- [ ] **Step 4: Full regression run**

```bash
uv run python -m pytest tests/ -q
```

Expected: all PASS.

- [ ] **Step 5: Run lint + type check if configured**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Fix any issues surfaced. Commit the fixes if needed.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_session_execution_end_to_end.py
git commit -m "test(integration): tmux-gated end-to-end for session execution modes"
```

---

## Self-review checklist

After implementing all tasks, verify:

**Spec coverage:**
- [x] §Decisions 1 (tmux-only live runtime): implicit in Tasks 10–11 (no subprocess runtime exists)
- [x] §Decisions 2 (manual kept): Task 9
- [x] §Decisions 3 (default is tmux): Task 1 (shipped default + Literal type)
- [x] §Decisions 4 (plan.md single kickoff source): Task 8 (`prep.run` reads plan.md and renders via `render_prompt`)
- [x] §Decisions 5 (mode at `spawn_config.invocation.runtime`): Task 1
- [x] §Decisions 6 (skills copied, not symlinked): Task 6
- [x] §Decisions 7 (planning artifacts referenced via project-tracking worktree): Task 7 (CLAUDE.md template)
- [x] §Decisions 8 (dual-PR at complete with merge policy): Tasks 15–17
- [x] §Architecture (3 layers): Tasks 4 (protocol), 5–8 (prep), 9–11 (runtimes)
- [x] §Schema changes: Tasks 1, 2
- [x] §Prep pipeline: Tasks 5–8
- [x] §TmuxRuntime: Tasks 10, 11
- [x] §ManualRuntime: Task 9
- [x] §`session attach`: Task 13
- [x] §Dual-PR: Tasks 15–17
- [x] §Error handling (tmux missing, skill not in package, CLAUDE.md backup, ready-probe timeout, partial PR success): Tasks 6, 7, 10, 12, 15
- [x] §Testing (per-runtime unit, dispatcher, integration gated): Tasks 4, 9, 10, 11, 18
- [x] §Migration (pid fallback): Task 14

**Type consistency:** `PreppedSession`, `RuntimeStartResult`, `AttachCommand` (union of `AttachExec`/`AttachInstruction`), `SessionRuntime` protocol, `RUNTIMES` registry — same names used throughout Tasks 4–14.

**Placeholder scan:** No TODO, TBD, "add appropriate error handling", or "similar to Task N" — all code blocks are complete.

**Follow-ups named in the spec but out-of-scope for this plan:**
- Container runtime (future `SessionRuntime` impl slots in via the registry)
- Per-agent-type boot preamble (agent.yaml field)
- PR review automation inside tripwire
- Auto-sync on mid-session plan.md edits

---

## Rollout

After the final commit, run one end-to-end smoke test against a real fresh project:

1. `tripwire init --non-interactive --no-git` in a scratch dir.
2. Author a session.yaml with `repos: [code-repo]` and `agent: backend-coder`.
3. `tripwire session queue`; `tripwire session spawn` → observe tmux session created, skills mounted, CLAUDE.md present.
4. `tripwire session attach` → tmux attach lands you in an interactive claude inside the worktree.
5. `tripwire session abandon` → tmux session gone.
6. Set `spawn_config.invocation.runtime: manual` on a second session; `tripwire session spawn` → prints the command; manually launching it works.
7. With a committed change in a worktree, `tripwire session complete` → PR opened via gh.

Then merge `feat/v0.7.2-tmux` into main.
