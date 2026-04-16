# Session Spawn, Agenda, and Worktree Isolation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local session execution (`spawn`), lifecycle management (`queue`, `pause`, `abandon`, `cleanup`), session-axis agenda, and git worktree isolation to keel.

**Architecture:** New CLI subcommands under `keel session`. Spawn creates git worktrees per repo and launches `claude -p` as a background process. Agenda builds a dependency DAG from `blocked_by_sessions` and computes launchable sessions + critical path. Three new core modules (`git_helpers`, `process_helpers`, `session_agenda`) plus extraction of readiness logic from the CLI into `session_readiness`.

**Tech Stack:** Python 3.12, Click (CLI), Pydantic (models), pytest, git worktrees

**Spec:** `docs/superpowers/specs/2026-04-16-session-spawn-agenda-worktrees-design.md`

---

### Task 1: Session model updates

Extend `RuntimeState` with new fields and add `WorktreeEntry` model. Add new statuses to the enum YAML.

**Files:**
- Modify: `src/keel/models/session.py:36-47`
- Modify: `src/keel/templates/enums/session_status.yaml`
- Test: `tests/unit/test_models.py`

- [ ] **Step 1: Write failing tests for new model fields**

Add to `tests/unit/test_models.py`:

```python
class TestRuntimeStateExtended:
    def test_worktree_entry_roundtrip(self):
        from keel.models.session import WorktreeEntry

        entry = WorktreeEntry(
            repo="SeidoAI/keel",
            clone_path="/home/user/keel",
            worktree_path="/home/user/keel-wt-api-endpoints",
            branch="feat/api-endpoints",
        )
        assert entry.repo == "SeidoAI/keel"
        assert entry.branch == "feat/api-endpoints"

    def test_runtime_state_with_worktrees(self):
        from keel.models.session import RuntimeState, WorktreeEntry

        rs = RuntimeState(
            worktrees=[
                WorktreeEntry(
                    repo="SeidoAI/keel",
                    clone_path="/tmp/keel",
                    worktree_path="/tmp/keel-wt-test",
                    branch="feat/test",
                )
            ],
            pid=12345,
            claude_session_id="abc-123",
            started_at="2026-04-16T10:30:00Z",
            log_path="/tmp/test.log",
        )
        assert len(rs.worktrees) == 1
        assert rs.pid == 12345
        assert rs.log_path == "/tmp/test.log"

    def test_runtime_state_defaults_empty(self):
        from keel.models.session import RuntimeState

        rs = RuntimeState()
        assert rs.worktrees == []
        assert rs.pid is None
        assert rs.started_at is None
        assert rs.log_path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_models.py::TestRuntimeStateExtended -v`
Expected: FAIL — `WorktreeEntry` doesn't exist, `RuntimeState` rejects extra fields

- [ ] **Step 3: Implement model changes**

In `src/keel/models/session.py`, add `WorktreeEntry` class before `RuntimeState` and extend `RuntimeState`:

```python
class WorktreeEntry(BaseModel):
    """One git worktree created for a session spawn."""

    model_config = ConfigDict(extra="forbid")

    repo: str  # GitHub slug, e.g. "SeidoAI/keel"
    clone_path: str  # absolute path to the original clone
    worktree_path: str  # absolute path to the worktree directory
    branch: str  # branch checked out in the worktree


class RuntimeState(BaseModel):
    """Session-wide runtime handles, persisted across container restarts."""

    model_config = ConfigDict(extra="forbid")

    claude_session_id: str | None = None
    langgraph_thread_id: str | None = None
    workspace_volume: str | None = None
    worktrees: list[WorktreeEntry] = Field(default_factory=list)
    pid: int | None = None
    started_at: datetime | str | None = None
    log_path: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_models.py::TestRuntimeStateExtended -v`
Expected: PASS

- [ ] **Step 5: Update session_status.yaml**

Add `queued`, `executing`, `paused`, `abandoned` to `src/keel/templates/enums/session_status.yaml`:

```yaml
  - id: queued
    label: Queued
    color: cyan
  - id: executing
    label: Executing
    color: blue
  - id: paused
    label: Paused
    color: yellow
  - id: abandoned
    label: Abandoned
    color: gray
```

Insert `queued` after `planned`, `executing` after `queued`, `paused` after `re_engaged`, `abandoned` after `failed`.

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/keel/models/session.py src/keel/templates/enums/session_status.yaml tests/unit/test_models.py
git commit -m "feat: extend RuntimeState with worktree, pid, log fields + new session statuses"
```

---

### Task 2: git_helpers module

Git worktree operations and branch checks.

**Files:**
- Create: `src/keel/core/git_helpers.py`
- Test: `tests/unit/test_git_helpers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_git_helpers.py`:

```python
"""Git helper functions for worktree and branch operations."""

import subprocess
from pathlib import Path

import pytest

from keel.core.git_helpers import (
    branch_exists,
    worktree_add,
    worktree_list,
    worktree_path_for_session,
    worktree_remove,
)


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                     "commit", "--allow-empty", "-q", "-m", "init"], cwd=path, check=True)


class TestBranchExists:
    def test_main_exists(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        # Default branch (main or master) exists
        assert branch_exists(repo, "main") or branch_exists(repo, "master")

    def test_nonexistent_branch(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        assert branch_exists(repo, "does-not-exist") is False

    def test_created_branch(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        subprocess.run(["git", "branch", "feat/test"], cwd=repo, check=True)
        assert branch_exists(repo, "feat/test") is True


class TestWorktreePathForSession:
    def test_path_convention(self):
        clone = Path("/home/user/projects/keel")
        result = worktree_path_for_session(clone, "api-endpoints")
        assert result == Path("/home/user/projects/keel-wt-api-endpoints")

    def test_path_with_trailing_slash(self):
        clone = Path("/home/user/projects/keel/")
        result = worktree_path_for_session(clone, "api-endpoints")
        assert result == Path("/home/user/projects/keel-wt-api-endpoints")


class TestWorktreeAdd:
    def test_creates_worktree(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        worktree_add(repo, wt_path, "feat/test", "HEAD")
        assert wt_path.is_dir()
        assert (wt_path / ".git").exists()  # .git is a file in worktrees

    def test_branch_created(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        worktree_add(repo, wt_path, "feat/test", "HEAD")
        assert branch_exists(repo, "feat/test")


class TestWorktreeRemove:
    def test_removes_worktree(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        worktree_add(repo, wt_path, "feat/test", "HEAD")
        worktree_remove(repo, wt_path)
        assert not wt_path.exists()

    def test_remove_nonexistent_is_noop(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        # Should not raise
        worktree_remove(repo, wt_path)


class TestWorktreeList:
    def test_lists_created_worktree(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        worktree_add(repo, wt_path, "feat/test", "HEAD")
        paths = worktree_list(repo)
        wt_resolved = [str(p) for p in paths]
        assert str(wt_path.resolve()) in wt_resolved or str(wt_path) in wt_resolved
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_git_helpers.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement git_helpers.py**

Create `src/keel/core/git_helpers.py`:

```python
"""Git helper functions for worktree and branch operations."""

from __future__ import annotations

import subprocess
from pathlib import Path


def branch_exists(repo_path: Path, branch_name: str) -> bool:
    """Check whether a branch exists in the given repo."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--verify", f"refs/heads/{branch_name}"],
        capture_output=True,
    )
    return result.returncode == 0


def worktree_path_for_session(clone_path: Path, session_slug: str) -> Path:
    """Compute the worktree path for a session.

    Convention: ``<repo-parent>/<repo-name>-wt-<session-slug>/``
    """
    clone_resolved = clone_path.resolve()
    return clone_resolved.parent / f"{clone_resolved.name}-wt-{session_slug}"


def worktree_add(
    clone_path: Path,
    wt_path: Path,
    branch: str,
    base_ref: str,
) -> None:
    """Create a git worktree with a new branch."""
    subprocess.run(
        [
            "git", "-C", str(clone_path),
            "worktree", "add",
            str(wt_path),
            "-b", branch,
            base_ref,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def worktree_remove(clone_path: Path, wt_path: Path) -> None:
    """Remove a git worktree. No-op if it doesn't exist."""
    if not wt_path.exists():
        return
    subprocess.run(
        ["git", "-C", str(clone_path), "worktree", "remove", "--force", str(wt_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def worktree_prune(clone_path: Path) -> None:
    """Prune stale worktree references."""
    subprocess.run(
        ["git", "-C", str(clone_path), "worktree", "prune"],
        check=True,
        capture_output=True,
        text=True,
    )


def worktree_list(clone_path: Path) -> list[Path]:
    """List all worktree paths for a repo."""
    result = subprocess.run(
        ["git", "-C", str(clone_path), "worktree", "list", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line.split(" ", 1)[1]))
    return paths


def worktree_is_dirty(wt_path: Path) -> bool:
    """Check if a worktree has uncommitted changes."""
    result = subprocess.run(
        ["git", "-C", str(wt_path), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_git_helpers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/keel/core/git_helpers.py tests/unit/test_git_helpers.py
git commit -m "feat: add git_helpers module for worktree operations"
```

---

### Task 3: process_helpers module

Process alive check and SIGTERM helper.

**Files:**
- Create: `src/keel/core/process_helpers.py`
- Test: `tests/unit/test_process_helpers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_process_helpers.py`:

```python
"""Process helper functions."""

import os
import signal
import subprocess
import sys

from keel.core.process_helpers import is_alive, send_sigterm


class TestIsAlive:
    def test_current_process_is_alive(self):
        assert is_alive(os.getpid()) is True

    def test_nonexistent_pid(self):
        # PID 4_000_000 is unlikely to exist
        assert is_alive(4_000_000) is False


class TestSendSigterm:
    def test_sigterm_running_process(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            assert send_sigterm(proc.pid) is True
            proc.wait(timeout=5)
        finally:
            proc.kill()
            proc.wait()

    def test_sigterm_nonexistent_returns_false(self):
        assert send_sigterm(4_000_000) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_process_helpers.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement process_helpers.py**

Create `src/keel/core/process_helpers.py`:

```python
"""Process helper functions for session lifecycle management."""

from __future__ import annotations

import os
import signal


def is_alive(pid: int) -> bool:
    """Check whether a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def send_sigterm(pid: int) -> bool:
    """Send SIGTERM to a process. Returns True if the process existed."""
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_process_helpers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/keel/core/process_helpers.py tests/unit/test_process_helpers.py
git commit -m "feat: add process_helpers module for PID checks and SIGTERM"
```

---

### Task 4: session_readiness module

Extract `_compute_readiness` from CLI to a shared core module. Add spawn-specific checks.

**Files:**
- Create: `src/keel/core/session_readiness.py`
- Modify: `src/keel/cli/session.py:161-262`
- Test: `tests/unit/test_session_readiness.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_session_readiness.py`:

```python
"""Session readiness checks (shared between queue, spawn, check)."""

from pathlib import Path

import pytest

from keel.core.session_readiness import check_readiness


class TestCheckReadiness:
    def test_missing_session_raises(self, tmp_path_project):
        with pytest.raises(FileNotFoundError):
            check_readiness(tmp_path_project, "nonexistent", kind="check")

    def test_minimal_session_missing_plan(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", plan=False)
        report = check_readiness(tmp_path_project, "s1", kind="check")
        assert not report.ready
        errors = [i for i in report.items if not i.passing]
        assert any("plan" in i.label for i in errors)

    def test_session_with_plan_and_handoff_is_ready(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "s1", plan=True)
        write_handoff_yaml(tmp_path_project, "s1")
        report = check_readiness(tmp_path_project, "s1", kind="check")
        assert report.ready

    def test_spawn_kind_checks_clone_and_claude(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(
            tmp_path_project, "s1", plan=True,
            repos=[{"repo": "SeidoAI/keel", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")
        report = check_readiness(tmp_path_project, "s1", kind="spawn")
        # Should have a warning/error about missing local clone
        clone_items = [i for i in report.items if "clone" in i.label.lower() or "local" in i.label.lower()]
        assert len(clone_items) > 0

    def test_blocked_by_incomplete_sessions(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "dep", plan=True, status="planned")
        save_test_session(
            tmp_path_project, "s1", plan=True,
            blocked_by_sessions=["dep"],
        )
        write_handoff_yaml(tmp_path_project, "s1")
        report = check_readiness(tmp_path_project, "s1", kind="queue")
        assert not report.ready
        blocker_items = [i for i in report.items if "dep" in i.label]
        assert len(blocker_items) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_readiness.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement session_readiness.py**

Create `src/keel/core/session_readiness.py`:

```python
"""Session readiness checks, shared by queue, spawn, and session check.

Extracted from ``keel.cli.session._compute_readiness`` so that all three
commands share one source of truth.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml as _yaml

from keel.core.handoff_store import handoff_exists, load_handoff
from keel.core.session_store import load_session
from keel.core.store import load_issue, load_project
from keel.models.manifest import ArtifactManifest


@dataclass
class ReadinessItem:
    label: str
    passing: bool
    severity: str  # "error" | "warning"
    fix_hint: str | None = None


@dataclass
class ReadinessReport:
    ready: bool
    items: list[ReadinessItem] = field(default_factory=list)


def check_readiness(
    project_dir: Path,
    session_id: str,
    *,
    kind: Literal["queue", "spawn", "check"] = "check",
) -> ReadinessReport:
    """Compute readiness for a session.

    Raises FileNotFoundError if the session doesn't exist.
    """
    session = load_session(project_dir, session_id)
    items: list[ReadinessItem] = []

    # 1. Required planning artifacts (per manifest).
    manifest_path = project_dir / "templates" / "artifacts" / "manifest.yaml"
    if manifest_path.exists():
        manifest = ArtifactManifest.model_validate(
            _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        )
        sess_dir = project_dir / "sessions" / session_id
        for entry in manifest.artifacts:
            if entry.produced_at != "planning" or entry.owned_by != "pm":
                continue
            if not entry.required:
                continue
            present = (sess_dir / entry.file).is_file()
            items.append(
                ReadinessItem(
                    label=f"planning artifact: {entry.file}",
                    passing=present,
                    severity="error",
                    fix_hint=(
                        None if present else f"Write {entry.file} from {entry.template}"
                    ),
                )
            )

    # 2. Blockers on issues.
    for issue_key in session.issues:
        try:
            issue = load_issue(project_dir, issue_key)
        except FileNotFoundError:
            items.append(
                ReadinessItem(
                    label=f"issue {issue_key} referenced by session not found",
                    passing=False,
                    severity="error",
                )
            )
            continue
        for blocker_key in issue.blocked_by or []:
            try:
                blocker = load_issue(project_dir, blocker_key)
            except FileNotFoundError:
                items.append(
                    ReadinessItem(
                        label=f"blocker {blocker_key} referenced by {issue_key} not found",
                        passing=False,
                        severity="error",
                    )
                )
                continue
            if blocker.status != "done":
                items.append(
                    ReadinessItem(
                        label=f"blocker: {blocker_key} ({blocker.status})",
                        passing=False,
                        severity="error",
                        fix_hint=f"Wait for {blocker_key} to reach status=done",
                    )
                )

    # 3. Blocked-by-sessions check.
    for dep_id in session.blocked_by_sessions:
        try:
            dep = load_session(project_dir, dep_id)
        except FileNotFoundError:
            items.append(
                ReadinessItem(
                    label=f"blocked_by_sessions: {dep_id} not found",
                    passing=False,
                    severity="warning",
                    fix_hint=f"Session {dep_id} does not exist",
                )
            )
            continue
        if dep.status != "completed":
            items.append(
                ReadinessItem(
                    label=f"blocked_by_sessions: {dep_id} ({dep.status})",
                    passing=False,
                    severity="error",
                    fix_hint=f"Wait for session {dep_id} to complete",
                )
            )

    # 4. Handoff.yaml presence + validity.
    if not handoff_exists(project_dir, session_id):
        items.append(
            ReadinessItem(
                label="handoff.yaml present",
                passing=False,
                severity="error",
                fix_hint="Run /pm-session-queue to create handoff.yaml",
            )
        )
    else:
        try:
            load_handoff(project_dir, session_id)
            items.append(
                ReadinessItem(
                    label="handoff.yaml valid + branch per convention",
                    passing=True,
                    severity="error",
                )
            )
        except Exception as exc:
            items.append(
                ReadinessItem(
                    label=f"handoff.yaml invalid: {exc}",
                    passing=False,
                    severity="error",
                    fix_hint="Fix handoff.yaml to match schema",
                )
            )

    # 5. Spawn-specific checks.
    if kind == "spawn":
        # Check local clones exist.
        try:
            project = load_project(project_dir)
        except Exception:
            project = None
        for rb in session.repos:
            local_path = None
            if project and hasattr(project, "repos") and project.repos:
                repo_config = project.repos.get(rb.repo) if isinstance(project.repos, dict) else None
                if repo_config and hasattr(repo_config, "local"):
                    local_path = repo_config.local
            if not local_path or not Path(local_path).expanduser().exists():
                items.append(
                    ReadinessItem(
                        label=f"local clone for {rb.repo}",
                        passing=False,
                        severity="error",
                        fix_hint=f"Set local clone path in project.yaml repos for {rb.repo}",
                    )
                )

        # Check claude CLI on PATH.
        if not shutil.which("claude"):
            items.append(
                ReadinessItem(
                    label="claude CLI on PATH",
                    passing=False,
                    severity="error",
                    fix_hint="Install Claude Code or add to PATH",
                )
            )

    errors = [i for i in items if not i.passing and i.severity == "error"]
    return ReadinessReport(ready=len(errors) == 0, items=items)
```

- [ ] **Step 4: Update CLI to use the new module**

In `src/keel/cli/session.py`, replace `_compute_readiness` and `ReadinessItem` with imports from the new module. Replace `_load_manifest_for_check` calls. Update the `check` subcommand to use `check_readiness`. Keep the CLI-level `ReadinessItem` import for the `check` command output formatting:

```python
# At the top of session.py, add:
from keel.core.session_readiness import check_readiness

# Replace the session_check_cmd body to use check_readiness:
# items = _compute_readiness(resolved, session_id)
# becomes:
# report = check_readiness(resolved, session_id, kind="check")
# items = report.items
```

Delete `_compute_readiness`, `_load_manifest_for_check`, and the local `ReadinessItem` class from `session.py`. Import `ReadinessItem` from `keel.core.session_readiness` instead.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_readiness.py tests/unit/test_session_cli.py -v`
Expected: PASS (both new and existing tests)

- [ ] **Step 6: Run full suite**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/keel/core/session_readiness.py src/keel/cli/session.py tests/unit/test_session_readiness.py
git commit -m "refactor: extract session readiness checks to core module"
```

---

### Task 5: session queue CLI

New `keel session queue <id>` subcommand.

**Files:**
- Modify: `src/keel/cli/session.py`
- Test: `tests/unit/test_session_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_session_cli.py`:

```python
class TestSessionQueue:
    def test_queue_sets_status(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "s1", plan=True)
        write_handoff_yaml(tmp_path_project, "s1")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd, ["queue", "s1", "--project-dir", str(tmp_path_project)]
        )
        assert result.exit_code == 0, result.output
        from keel.core.session_store import load_session
        s = load_session(tmp_path_project, "s1")
        assert s.status == "queued"

    def test_queue_rejects_non_planned(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "s1", plan=True, status="completed")
        write_handoff_yaml(tmp_path_project, "s1")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd, ["queue", "s1", "--project-dir", str(tmp_path_project)]
        )
        assert result.exit_code != 0

    def test_queue_fails_without_plan(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "s1", plan=False)
        write_handoff_yaml(tmp_path_project, "s1")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd, ["queue", "s1", "--project-dir", str(tmp_path_project)]
        )
        assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_cli.py::TestSessionQueue -v`
Expected: FAIL — `queue` subcommand doesn't exist

- [ ] **Step 3: Implement queue subcommand**

Add to `src/keel/cli/session.py`:

```python
@session_cmd.command("queue")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_queue_cmd(session_id: str, project_dir: Path) -> None:
    """Validate readiness and transition session to queued."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    session = load_session(resolved, session_id)
    if session.status != "planned":
        raise click.ClickException(
            f"session '{session_id}' is '{session.status}', must be 'planned' to queue"
        )

    report = check_readiness(resolved, session_id, kind="queue")
    if not report.ready:
        for item in report.items:
            if not item.passing:
                click.echo(f"  ✗ {item.label}")
                if item.fix_hint:
                    click.echo(f"    → {item.fix_hint}")
        raise click.ClickException("Not ready to queue — fix errors above")

    session.status = "queued"
    from datetime import datetime, timezone
    session.updated_at = datetime.now(tz=timezone.utc)
    from keel.core.session_store import save_session
    save_session(resolved, session)
    click.echo(f"Session '{session_id}' → queued")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_cli.py::TestSessionQueue -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/keel/cli/session.py tests/unit/test_session_cli.py
git commit -m "feat: add keel session queue command"
```

---

### Task 6: session spawn CLI

The main spawn command: creates worktrees, launches `claude -p`, updates session state.

**Files:**
- Modify: `src/keel/cli/session.py`
- Test: `tests/unit/test_session_spawn_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_session_spawn_cli.py`:

```python
"""Tests for keel session spawn."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from keel.cli.session import session_cmd
from keel.core.session_store import load_session


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=path, check=True,
    )


class TestSessionSpawn:
    def test_spawn_rejects_non_queued(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["spawn", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0
        assert "queued" in result.output.lower() or "status" in result.output.lower()

    def test_spawn_dry_run_no_side_effects(
        self, tmp_path, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        # Set up a git repo to use as the clone
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        save_test_session(
            tmp_path_project, "s1", plan=True, status="queued",
            repos=[{"repo": "SeidoAI/keel", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        with patch("shutil.which", return_value="/usr/bin/claude"):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--dry-run", "--project-dir", str(tmp_path_project)],
            )
        # Dry run should not crash; session stays queued
        s = load_session(tmp_path_project, "s1")
        assert s.status == "queued"

    def test_spawn_creates_worktree(
        self, tmp_path, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        save_test_session(
            tmp_path_project, "s1", plan=True, status="queued",
            repos=[{"repo": "SeidoAI/keel", "base_branch": "main",
                     "branch": "feat/s1"}],
        )
        write_handoff_yaml(tmp_path_project, "s1", branch="feat/s1")

        # Mock claude and the project repos lookup
        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch("keel.cli.session._resolve_clone_path", return_value=clone), \
             patch("keel.cli.session._launch_claude", return_value=99999):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.status == "executing"
        assert len(s.runtime_state.worktrees) == 1
        assert s.runtime_state.pid == 99999
        assert s.runtime_state.claude_session_id is not None

        # Worktree should exist on disk
        wt_path = Path(s.runtime_state.worktrees[0].worktree_path)
        assert wt_path.is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_spawn_cli.py -v`
Expected: FAIL — `spawn` subcommand doesn't exist

- [ ] **Step 3: Implement spawn subcommand**

Add to `src/keel/cli/session.py`:

```python
import shutil
import uuid as _uuid_mod
from datetime import datetime, timezone

from keel.core.git_helpers import worktree_add, worktree_path_for_session
from keel.core.session_store import load_session, save_session
from keel.models.session import EngagementEntry, WorktreeEntry


def _resolve_clone_path(project_dir: Path, repo_slug: str) -> Path | None:
    """Look up the local clone path for a repo from project.yaml."""
    try:
        project = load_project(project_dir)
    except Exception:
        return None
    if not project.repos or not isinstance(project.repos, dict):
        return None
    repo_cfg = project.repos.get(repo_slug)
    if repo_cfg is None:
        return None
    local = getattr(repo_cfg, "local", None)
    if local is None:
        return None
    p = Path(local).expanduser()
    return p if p.exists() else None


def _launch_claude(
    wt_path: Path,
    plan_content: str,
    session_id: str,
    session_name: str,
    branch: str,
    claude_session_id: str,
    max_turns: int,
    log_path: Path,
) -> int:
    """Launch ``claude -p`` as a background process. Returns PID."""
    import subprocess

    prompt = (
        f"{plan_content}\n\n"
        f"You are autonomous. Execute the plan above.\n"
        f"Stop only at the plan's stop-and-ask points.\n"
        f"Open a PR titled 'feat({session_id}): {session_name}' when done.\n"
        f"Report back as the final message."
    )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w")

    proc = subprocess.Popen(
        [
            "claude", "-p", prompt,
            "--session-id", claude_session_id,
            "--max-turns", str(max_turns),
            "--output-format", "json",
        ],
        cwd=str(wt_path),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return proc.pid


@session_cmd.command("spawn")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option("--max-turns-override", type=int, default=None)
@click.option("--log-dir", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--resume", is_flag=True, default=False)
def session_spawn_cmd(
    session_id: str,
    project_dir: Path,
    max_turns_override: int | None,
    log_dir: Path | None,
    dry_run: bool,
    resume: bool,
) -> None:
    """Create worktree(s), launch claude -p, transition to executing."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    session = load_session(resolved, session_id)

    # Status gate
    if resume:
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

    # Load plan
    from keel.core.paths import session_plan_path
    plan_path = session_plan_path(resolved, session_id)
    if not plan_path.is_file():
        raise click.ClickException(f"plan.md not found at {plan_path}")
    plan_content = plan_path.read_text(encoding="utf-8")

    # Load handoff for branch name
    from keel.core.handoff_store import load_handoff
    handoff = load_handoff(resolved, session_id)
    if handoff is None:
        raise click.ClickException("handoff.yaml not found")
    branch = handoff.branch

    # Resolve max_turns
    max_turns = max_turns_override or 200

    # Create worktrees (or reuse on --resume)
    worktree_entries: list[WorktreeEntry] = []
    primary_wt_path: Path | None = None

    if resume and session.runtime_state.worktrees:
        # Reuse existing worktrees
        for wt in session.runtime_state.worktrees:
            wt_path = Path(wt.worktree_path)
            if not wt_path.exists():
                raise click.ClickException(
                    f"Worktree {wt_path} no longer exists. "
                    f"Run 'keel session cleanup {session_id}' then spawn without --resume."
                )
            worktree_entries.append(wt)
            if primary_wt_path is None:
                primary_wt_path = wt_path
    else:
        for rb in session.repos:
            clone_path = _resolve_clone_path(resolved, rb.repo)
            if clone_path is None:
                raise click.ClickException(
                    f"No local clone for {rb.repo}. "
                    f"Set local path in project.yaml repos."
                )
            wt_path = worktree_path_for_session(clone_path, session_id)
            if wt_path.exists() and not resume:
                raise click.ClickException(
                    f"Worktree path {wt_path} already exists. "
                    f"Use --resume or 'keel session cleanup {session_id}'."
                )
            if not wt_path.exists():
                base_ref = rb.base_branch or "HEAD"
                worktree_add(clone_path, wt_path, branch, base_ref)
            worktree_entries.append(
                WorktreeEntry(
                    repo=rb.repo,
                    clone_path=str(clone_path),
                    worktree_path=str(wt_path),
                    branch=branch,
                )
            )
            if primary_wt_path is None:
                primary_wt_path = wt_path

    if dry_run:
        click.echo(f"Dry run — would spawn session '{session_id}'")
        click.echo(f"  Branch: {branch}")
        for wt in worktree_entries:
            click.echo(f"  Worktree: {wt.worktree_path}")
        click.echo(f"  Max turns: {max_turns}")
        return

    if primary_wt_path is None:
        raise click.ClickException("No repos configured for this session")

    # Generate claude session ID
    claude_sid = session.runtime_state.claude_session_id if resume else str(_uuid_mod.uuid4())

    # Log path
    if log_dir is None:
        log_dir = Path.home() / ".keel" / "logs"
    from keel.core.store import load_project as _lp
    try:
        proj = _lp(resolved)
        project_slug = proj.name.lower().replace(" ", "-")
    except Exception:
        project_slug = "unknown"
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_file = log_dir / project_slug / f"{session_id}-{ts}.log"

    # Launch
    pid = _launch_claude(
        wt_path=primary_wt_path,
        plan_content=plan_content,
        session_id=session_id,
        session_name=session.name,
        branch=branch,
        claude_session_id=claude_sid,
        max_turns=max_turns,
        log_path=log_file,
    )

    # Update session
    now = datetime.now(tz=timezone.utc)
    session.status = "executing"
    session.runtime_state.worktrees = worktree_entries
    session.runtime_state.pid = pid
    session.runtime_state.claude_session_id = claude_sid
    session.runtime_state.started_at = now.isoformat()
    session.runtime_state.log_path = str(log_file)
    session.updated_at = now
    session.engagements.append(
        EngagementEntry(
            started_at=now,
            trigger="re_engagement" if resume else "initial_launch",
        )
    )
    save_session(resolved, session)

    click.echo(f"Session '{session_id}' → executing")
    click.echo(f"  PID: {pid}")
    click.echo(f"  Branch: {branch}")
    click.echo(f"  Worktree: {primary_wt_path}")
    click.echo(f"  Log: {log_file}")
    click.echo(f"  Claude session: {claude_sid}")
    click.echo(f"\n  tail -f {log_file}")
```

Add the necessary imports at the top of `session.py`:

```python
from keel.core.store import load_project
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_spawn_cli.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/keel/cli/session.py tests/unit/test_session_spawn_cli.py
git commit -m "feat: add keel session spawn command with worktree isolation"
```

---

### Task 7: session pause and abandon

Lifecycle management commands.

**Files:**
- Modify: `src/keel/cli/session.py`
- Test: `tests/unit/test_session_lifecycle_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_session_lifecycle_cli.py`:

```python
"""Tests for pause, abandon, cleanup session lifecycle commands."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from keel.cli.session import session_cmd
from keel.core.session_store import load_session


class TestSessionPause:
    def test_pause_executing_session(
        self, tmp_path_project, save_test_session
    ):
        # Spawn a real process to pause
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"]
        )
        save_test_session(
            tmp_path_project, "s1", status="executing",
            runtime_state={"pid": proc.pid, "claude_session_id": "abc"},
        )
        try:
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["pause", "s1", "--project-dir", str(tmp_path_project)],
            )
            assert result.exit_code == 0, result.output
            s = load_session(tmp_path_project, "s1")
            assert s.status == "paused"
        finally:
            proc.kill()
            proc.wait()

    def test_pause_rejects_non_executing(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["pause", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0

    def test_pause_dead_process_sets_failed(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project, "s1", status="executing",
            runtime_state={"pid": 4_000_000, "claude_session_id": "abc"},
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["pause", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        s = load_session(tmp_path_project, "s1")
        assert s.status == "failed"


class TestSessionAbandon:
    def test_abandon_planned(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["abandon", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.status == "abandoned"

    def test_abandon_rejects_completed(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", status="completed")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["abandon", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0

    def test_abandon_executing_kills_process(
        self, tmp_path_project, save_test_session
    ):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"]
        )
        save_test_session(
            tmp_path_project, "s1", status="executing",
            runtime_state={"pid": proc.pid, "claude_session_id": "abc"},
        )
        try:
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["abandon", "s1", "--project-dir", str(tmp_path_project)],
            )
            assert result.exit_code == 0, result.output
            s = load_session(tmp_path_project, "s1")
            assert s.status == "abandoned"
        finally:
            proc.kill()
            proc.wait()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_lifecycle_cli.py -v`
Expected: FAIL — subcommands don't exist

- [ ] **Step 3: Implement pause and abandon**

Add to `src/keel/cli/session.py`:

```python
from keel.core.process_helpers import is_alive, send_sigterm


@session_cmd.command("pause")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_pause_cmd(session_id: str, project_dir: Path) -> None:
    """SIGTERM the claude process, transition to paused."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    session = load_session(resolved, session_id)
    if session.status != "executing":
        raise click.ClickException(
            f"session '{session_id}' is '{session.status}', must be 'executing' to pause"
        )

    pid = session.runtime_state.pid
    now = datetime.now(tz=timezone.utc)

    if pid and is_alive(pid):
        send_sigterm(pid)
        session.status = "paused"
        click.echo(f"Session '{session_id}' → paused (SIGTERM sent to PID {pid})")
    else:
        session.status = "failed"
        click.echo(
            f"Warning: PID {pid} not found — session '{session_id}' → failed"
        )

    session.updated_at = now
    save_session(resolved, session)


@session_cmd.command("abandon")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_abandon_cmd(session_id: str, project_dir: Path) -> None:
    """Kill the process if running, transition to abandoned."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    session = load_session(resolved, session_id)
    if session.status in ("completed", "abandoned"):
        raise click.ClickException(
            f"session '{session_id}' is already '{session.status}'"
        )

    pid = session.runtime_state.pid
    if pid and session.status == "executing" and is_alive(pid):
        send_sigterm(pid)
        click.echo(f"Sent SIGTERM to PID {pid}")

    session.status = "abandoned"
    session.updated_at = datetime.now(tz=timezone.utc)
    save_session(resolved, session)
    click.echo(f"Session '{session_id}' → abandoned")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_lifecycle_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/keel/cli/session.py tests/unit/test_session_lifecycle_cli.py
git commit -m "feat: add keel session pause and abandon commands"
```

---

### Task 8: session cleanup

Worktree removal command.

**Files:**
- Modify: `src/keel/cli/session.py`
- Test: `tests/unit/test_session_lifecycle_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_session_lifecycle_cli.py`:

```python
def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=path, check=True,
    )


class TestSessionCleanup:
    def test_cleanup_removes_completed_worktree(self, tmp_path, tmp_path_project, save_test_session):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)
        wt_path = tmp_path / "clone-wt-s1"
        subprocess.run(
            ["git", "-C", str(clone), "worktree", "add", str(wt_path), "-b", "feat/s1", "HEAD"],
            check=True, capture_output=True,
        )
        save_test_session(
            tmp_path_project, "s1", status="completed",
            runtime_state={
                "worktrees": [{
                    "repo": "X/Y",
                    "clone_path": str(clone),
                    "worktree_path": str(wt_path),
                    "branch": "feat/s1",
                }]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        assert not wt_path.exists()

    def test_cleanup_skips_failed(self, tmp_path, tmp_path_project, save_test_session):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)
        wt_path = tmp_path / "clone-wt-s1"
        subprocess.run(
            ["git", "-C", str(clone), "worktree", "add", str(wt_path), "-b", "feat/s1", "HEAD"],
            check=True, capture_output=True,
        )
        save_test_session(
            tmp_path_project, "s1", status="failed",
            runtime_state={
                "worktrees": [{
                    "repo": "X/Y",
                    "clone_path": str(clone),
                    "worktree_path": str(wt_path),
                    "branch": "feat/s1",
                }]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        # Worktree should still exist — failed not cleaned by default
        assert wt_path.exists()

    def test_cleanup_explicit_id(self, tmp_path, tmp_path_project, save_test_session):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)
        wt_path = tmp_path / "clone-wt-s1"
        subprocess.run(
            ["git", "-C", str(clone), "worktree", "add", str(wt_path), "-b", "feat/s1", "HEAD"],
            check=True, capture_output=True,
        )
        save_test_session(
            tmp_path_project, "s1", status="failed",
            runtime_state={
                "worktrees": [{
                    "repo": "X/Y",
                    "clone_path": str(clone),
                    "worktree_path": str(wt_path),
                    "branch": "feat/s1",
                }]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert not wt_path.exists()

    def test_cleanup_refuses_dirty(self, tmp_path, tmp_path_project, save_test_session):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)
        wt_path = tmp_path / "clone-wt-s1"
        subprocess.run(
            ["git", "-C", str(clone), "worktree", "add", str(wt_path), "-b", "feat/s1", "HEAD"],
            check=True, capture_output=True,
        )
        # Make the worktree dirty
        (wt_path / "dirty.txt").write_text("uncommitted")
        subprocess.run(["git", "add", "dirty.txt"], cwd=wt_path, check=True)

        save_test_session(
            tmp_path_project, "s1", status="completed",
            runtime_state={
                "worktrees": [{
                    "repo": "X/Y",
                    "clone_path": str(clone),
                    "worktree_path": str(wt_path),
                    "branch": "feat/s1",
                }]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "--project-dir", str(tmp_path_project)],
        )
        # Should warn but not crash; worktree still exists
        assert wt_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_lifecycle_cli.py::TestSessionCleanup -v`
Expected: FAIL

- [ ] **Step 3: Implement cleanup subcommand**

Add to `src/keel/cli/session.py`:

```python
from keel.core.git_helpers import worktree_is_dirty, worktree_prune, worktree_remove


@session_cmd.command("cleanup")
@click.argument("session_id", required=False, default=None)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option("--all", "clean_all", is_flag=True, default=False,
              help="Clean ALL session worktrees")
@click.option("--force", is_flag=True, default=False,
              help="Skip dirty-worktree check")
def session_cleanup_cmd(
    session_id: str | None,
    project_dir: Path,
    clean_all: bool,
    force: bool,
) -> None:
    """Remove worktrees for completed/abandoned sessions."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    clones_to_prune: set[str] = set()

    if session_id:
        targets = [s for s in sessions if s.id == session_id]
        if not targets:
            raise click.ClickException(f"session '{session_id}' not found")
    elif clean_all:
        if not click.confirm("Remove ALL session worktrees?"):
            return
        targets = sessions
    else:
        # Default: completed + abandoned only
        targets = [s for s in sessions if s.status in ("completed", "abandoned")]

    cleaned = 0
    for session in targets:
        for wt in session.runtime_state.worktrees:
            wt_path = Path(wt.worktree_path)
            if not wt_path.exists():
                continue
            if not force and worktree_is_dirty(wt_path):
                click.echo(
                    f"  Skipping {wt_path} — uncommitted changes (use --force)"
                )
                continue
            clone_path = Path(wt.clone_path)
            worktree_remove(clone_path, wt_path)
            clones_to_prune.add(str(clone_path))
            cleaned += 1

        # Clear runtime_state worktrees
        if session.runtime_state.worktrees:
            remaining = [
                wt for wt in session.runtime_state.worktrees
                if Path(wt.worktree_path).exists()
            ]
            session.runtime_state.worktrees = remaining
            save_session(resolved, session)

    # Prune stale refs
    for clone_str in clones_to_prune:
        worktree_prune(Path(clone_str))

    click.echo(f"Cleaned {cleaned} worktree(s)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_lifecycle_cli.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/keel/cli/session.py tests/unit/test_session_lifecycle_cli.py
git commit -m "feat: add keel session cleanup command"
```

---

### Task 9: session_agenda module

DAG computation, launchable resolution, critical path, recommendations.

**Files:**
- Create: `src/keel/core/session_agenda.py`
- Test: `tests/unit/test_session_agenda.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_session_agenda.py`:

```python
"""Session agenda DAG computation and recommendations."""

import pytest

from keel.core.session_agenda import (
    AgendaReport,
    CycleDetectedError,
    build_agenda,
)


def _session(id: str, status: str = "planned", blocked_by: list[str] | None = None):
    """Minimal session dict for agenda input."""
    return {"id": id, "status": status, "blocked_by_sessions": blocked_by or []}


class TestBuildAgenda:
    def test_no_sessions(self):
        report = build_agenda([])
        assert report.totals["planned"] == 0
        assert report.launchable == []
        assert report.blocked == []

    def test_single_unblocked_session(self):
        report = build_agenda([_session("s1")])
        assert len(report.launchable) == 1
        assert report.launchable[0].id == "s1"
        assert report.blocked == []

    def test_two_independent_sessions(self):
        report = build_agenda([_session("s1"), _session("s2")])
        assert len(report.launchable) == 2

    def test_blocked_session(self):
        report = build_agenda([
            _session("s1"),
            _session("s2", blocked_by=["s1"]),
        ])
        assert len(report.launchable) == 1
        assert report.launchable[0].id == "s1"
        assert len(report.blocked) == 1
        assert report.blocked[0].id == "s2"

    def test_completed_blocker_unblocks(self):
        report = build_agenda([
            _session("s1", status="completed"),
            _session("s2", blocked_by=["s1"]),
        ])
        assert len(report.launchable) == 1
        assert report.launchable[0].id == "s2"

    def test_critical_path_linear(self):
        report = build_agenda([
            _session("s1"),
            _session("s2", blocked_by=["s1"]),
            _session("s3", blocked_by=["s2"]),
        ])
        assert report.critical_path == ["s1", "s2", "s3"]

    def test_critical_path_picks_longest(self):
        report = build_agenda([
            _session("s1"),
            _session("s2"),
            _session("s3", blocked_by=["s1"]),
            _session("s4", blocked_by=["s3"]),
        ])
        # s1 → s3 → s4 is longer than s2 alone
        assert report.critical_path == ["s1", "s3", "s4"]

    def test_cycle_detected(self):
        with pytest.raises(CycleDetectedError) as exc_info:
            build_agenda([
                _session("s1", blocked_by=["s2"]),
                _session("s2", blocked_by=["s1"]),
            ])
        assert "s1" in str(exc_info.value) or "s2" in str(exc_info.value)

    def test_orphan_blocker_treated_as_unblocked(self):
        report = build_agenda([
            _session("s1", blocked_by=["nonexistent"]),
        ])
        assert len(report.launchable) == 1
        assert len(report.warnings) > 0

    def test_recommendations_by_blast_radius(self):
        report = build_agenda([
            _session("s1"),  # unblocks s3, s4
            _session("s2"),  # unblocks nothing
            _session("s3", blocked_by=["s1"]),
            _session("s4", blocked_by=["s1"]),
        ])
        assert report.recommendations[0].session_id == "s1"

    def test_totals(self):
        report = build_agenda([
            _session("s1", status="completed"),
            _session("s2", status="executing"),
            _session("s3"),
            _session("s4", blocked_by=["s3"]),
        ])
        assert report.totals["completed"] == 1
        assert report.totals["executing"] == 1
        assert report.totals["planned"] == 2

    def test_executing_not_launchable(self):
        report = build_agenda([_session("s1", status="executing")])
        assert len(report.launchable) == 0

    def test_all_completed(self):
        report = build_agenda([
            _session("s1", status="completed"),
            _session("s2", status="completed"),
        ])
        assert report.all_completed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_agenda.py -v`
Expected: FAIL

- [ ] **Step 3: Implement session_agenda.py**

Create `src/keel/core/session_agenda.py`:

```python
"""Session agenda: DAG computation, launchable resolution, critical path."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


class CycleDetectedError(Exception):
    pass


@dataclass
class SessionInfo:
    id: str
    status: str
    blocked_by: list[str]
    dependents: list[str] = field(default_factory=list)
    is_launchable: bool = False
    critical_path_position: int | None = None


@dataclass
class Recommendation:
    session_id: str
    rank: int
    rationale: str


@dataclass
class AgendaReport:
    totals: dict[str, int] = field(default_factory=dict)
    launchable: list[SessionInfo] = field(default_factory=list)
    blocked: list[SessionInfo] = field(default_factory=list)
    in_flight: list[SessionInfo] = field(default_factory=list)
    completed_sessions: list[SessionInfo] = field(default_factory=list)
    critical_path: list[str] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    all_completed: bool = False


LAUNCHABLE_STATUSES = {"planned", "queued"}
IN_FLIGHT_STATUSES = {"executing", "active", "paused"}
TERMINAL_STATUSES = {"completed", "abandoned"}
COMPLETED_STATUS = "completed"


def build_agenda(sessions: list[dict]) -> AgendaReport:
    """Build an agenda report from a list of session dicts.

    Each dict must have: id, status, blocked_by_sessions.
    """
    report = AgendaReport()
    if not sessions:
        return report

    # Index sessions
    by_id: dict[str, SessionInfo] = {}
    for s in sessions:
        info = SessionInfo(
            id=s["id"],
            status=s["status"],
            blocked_by=s.get("blocked_by_sessions", []),
        )
        by_id[info.id] = info

    # Build adjacency + dependents
    for info in by_id.values():
        resolved_blockers = []
        for dep_id in info.blocked_by:
            if dep_id not in by_id:
                report.warnings.append(
                    f"Session '{info.id}' blocked by unknown session '{dep_id}'"
                )
                continue
            resolved_blockers.append(dep_id)
            by_id[dep_id].dependents.append(info.id)
        info.blocked_by = resolved_blockers

    # Cycle detection via topological sort (Kahn's algorithm)
    in_degree: dict[str, int] = {sid: 0 for sid in by_id}
    for info in by_id.values():
        for dep_id in info.blocked_by:
            in_degree[info.id] += 1

    queue: list[str] = [sid for sid, deg in in_degree.items() if deg == 0]
    topo_order: list[str] = []

    while queue:
        sid = queue.pop(0)
        topo_order.append(sid)
        for dep_id in by_id[sid].dependents:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                queue.append(dep_id)

    if len(topo_order) != len(by_id):
        remaining = set(by_id.keys()) - set(topo_order)
        raise CycleDetectedError(
            f"Cycle detected among sessions: {', '.join(sorted(remaining))}"
        )

    # Resolve launchable
    for info in by_id.values():
        all_blockers_done = all(
            by_id[dep_id].status == COMPLETED_STATUS
            for dep_id in info.blocked_by
        )
        if info.status in LAUNCHABLE_STATUSES and all_blockers_done:
            info.is_launchable = True
            report.launchable.append(info)
        elif info.status in IN_FLIGHT_STATUSES:
            report.in_flight.append(info)
        elif info.status in TERMINAL_STATUSES:
            report.completed_sessions.append(info)
        else:
            report.blocked.append(info)

    # Critical path (longest path in DAG)
    dist: dict[str, int] = {sid: 0 for sid in by_id}
    pred: dict[str, str | None] = {sid: None for sid in by_id}

    for sid in topo_order:
        for dep_id in by_id[sid].dependents:
            if dist[sid] + 1 > dist[dep_id]:
                dist[dep_id] = dist[sid] + 1
                pred[dep_id] = sid

    if dist:
        end = max(dist, key=lambda s: dist[s])
        path: list[str] = []
        current: str | None = end
        while current is not None:
            path.append(current)
            current = pred[current]
        report.critical_path = list(reversed(path))

        # Set critical path positions
        for i, sid in enumerate(report.critical_path):
            by_id[sid].critical_path_position = i + 1

    # Recommendations (launchable sessions ranked by blast radius)
    def _blast_radius(sid: str) -> int:
        """Count sessions transitively unblocked."""
        visited: set[str] = set()
        stack = [sid]
        while stack:
            current = stack.pop()
            for dep in by_id[current].dependents:
                if dep not in visited:
                    visited.add(dep)
                    stack.append(dep)
        return len(visited)

    ranked = sorted(
        report.launchable,
        key=lambda info: _blast_radius(info.id),
        reverse=True,
    )
    for i, info in enumerate(ranked[:5]):
        radius = _blast_radius(info.id)
        on_cp = info.id in report.critical_path
        parts = []
        if radius > 0:
            parts.append(f"unblocks {radius}")
        if on_cp:
            parts.append("on critical path")
        report.recommendations.append(
            Recommendation(
                session_id=info.id,
                rank=i + 1,
                rationale=", ".join(parts) if parts else "no dependents",
            )
        )

    # Totals
    status_counts: dict[str, int] = defaultdict(int)
    for info in by_id.values():
        status_counts[info.status] += 1
    report.totals = dict(status_counts)

    report.all_completed = all(
        info.status in TERMINAL_STATUSES for info in by_id.values()
    )

    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_agenda.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/keel/core/session_agenda.py tests/unit/test_session_agenda.py
git commit -m "feat: add session_agenda module for DAG computation and recommendations"
```

---

### Task 10: session agenda CLI

Text and JSON output for the agenda command.

**Files:**
- Modify: `src/keel/cli/session.py`
- Test: `tests/unit/test_session_cli.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_session_cli.py`:

```python
class TestSessionAgenda:
    def test_agenda_empty_project(self, tmp_path_project):
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert "no sessions" in result.output.lower()

    def test_agenda_shows_launchable(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", status="planned")
        save_test_session(tmp_path_project, "s2", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert "s1" in result.output
        assert "s2" in result.output
        assert "LAUNCHABLE" in result.output

    def test_agenda_shows_blocked(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", status="planned")
        save_test_session(
            tmp_path_project, "s2", status="planned",
            blocked_by_sessions=["s1"],
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert "BLOCKED" in result.output

    def test_agenda_json_format(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project), "--format", "json"],
        )
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert "sessions" in data
        assert "recommendations" in data

    def test_agenda_all_completed(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(tmp_path_project, "s1", status="completed")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert "all sessions complete" in result.output.lower()

    def test_agenda_cycle_exits_nonzero(
        self, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project, "s1", status="planned",
            blocked_by_sessions=["s2"],
        )
        save_test_session(
            tmp_path_project, "s2", status="planned",
            blocked_by_sessions=["s1"],
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0
        assert "cycle" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_cli.py::TestSessionAgenda -v`
Expected: FAIL

- [ ] **Step 3: Implement agenda subcommand**

Add to `src/keel/cli/session.py`:

```python
from keel.core.session_agenda import AgendaReport, CycleDetectedError, build_agenda


@session_cmd.command("agenda")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.option("--status", "filter_status", default=None)
def session_agenda_cmd(
    project_dir: Path, output_format: str, filter_status: str | None
) -> None:
    """Session dependency DAG with launch recommendations."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    if not sessions:
        click.echo("No sessions found.")
        return

    session_dicts = [
        {
            "id": s.id,
            "status": s.status,
            "blocked_by_sessions": s.blocked_by_sessions,
        }
        for s in sessions
    ]

    try:
        report = build_agenda(session_dicts)
    except CycleDetectedError as exc:
        raise click.ClickException(str(exc)) from exc

    if output_format == "json":
        from dataclasses import asdict
        payload = {
            "totals": report.totals,
            "critical_path": report.critical_path,
            "sessions": [
                {
                    "id": info.id,
                    "status": info.status,
                    "blocked_by": info.blocked_by,
                    "dependents": info.dependents,
                    "is_launchable": info.is_launchable,
                    "critical_path_position": info.critical_path_position,
                }
                for info in (
                    report.launchable
                    + report.blocked
                    + report.in_flight
                    + report.completed_sessions
                )
            ],
            "recommendations": [asdict(r) for r in report.recommendations],
            "warnings": report.warnings,
        }
        click.echo(json.dumps(payload, indent=2))
        return

    # Text output
    from keel.core.store import load_project as _lp
    try:
        proj = _lp(resolved)
        proj_name = proj.name
    except Exception:
        proj_name = "project"

    total_count = sum(report.totals.values())
    click.echo(f"{proj_name} — {total_count} sessions")
    parts = []
    for status, count in sorted(report.totals.items()):
        parts.append(f"{count} {status}")
    click.echo(f"  {', '.join(parts)}")

    if report.all_completed:
        click.echo("\nAll sessions complete.")
        return

    if report.critical_path and len(report.critical_path) > 1:
        cp = " → ".join(report.critical_path)
        click.echo(f"\n  critical path: {cp} ({len(report.critical_path)} sessions)")

    if report.launchable:
        click.echo("\nLAUNCHABLE (all blockers completed):")
        for info in report.launchable:
            blocker_text = "no blockers" if not info.blocked_by else f"blockers done"
            click.echo(f"  {info.id:<30} {info.status:<10} {blocker_text}")

    if report.in_flight:
        click.echo("\nIN FLIGHT:")
        for info in report.in_flight:
            click.echo(f"  {info.id:<30} {info.status}")

    if report.blocked:
        click.echo("\nBLOCKED:")
        for info in report.blocked:
            click.echo(
                f"  {info.id:<30} {info.status:<10} blocked by: {', '.join(info.blocked_by)}"
            )

    if report.recommendations:
        click.echo("\nRecommended next:")
        for rec in report.recommendations:
            click.echo(f"  {rec.rank}. {rec.session_id}  ({rec.rationale})")

    if report.warnings:
        click.echo("\nWarnings:")
        for w in report.warnings:
            click.echo(f"  ⚠ {w}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/unit/test_session_cli.py::TestSessionAgenda -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/keel/cli/session.py tests/unit/test_session_cli.py
git commit -m "feat: add keel session agenda command"
```

---

### Task 11: Slash commands

Rename pm-session-launch to pm-session-queue, add pm-session-spawn and pm-session-agenda.

**Files:**
- Modify: `src/keel/templates/commands/pm-session-launch.md` (rename)
- Create: `src/keel/templates/commands/pm-session-queue.md`
- Create: `src/keel/templates/commands/pm-session-spawn.md`
- Create: `src/keel/templates/commands/pm-session-agenda.md`

- [ ] **Step 1: Create pm-session-queue (rename from pm-session-launch)**

Read `pm-session-launch.md`, then write `pm-session-queue.md` with updated name and references:

```markdown
---
name: pm-session-queue
description: Transition session to queued after readiness check.
argument-hint: "<session-id>"
---

You are the project manager. Load the project-manager skill if not
active.

Session to queue:
$ARGUMENTS

Workflow:

1. Run `keel session check $ARGUMENTS` to verify launch-readiness.
   If exit code is non-zero, report the punch list and stop. Do NOT
   proceed with outstanding errors.
2. Run `keel lint handoff $ARGUMENTS` and surface findings. Any
   error-severity finding blocks queueing.
3. Run `keel brief` to load project state.
4. Read `sessions/$ARGUMENTS/session.yaml` and `handoff.yaml`.
5. Run `keel session queue $ARGUMENTS`. This validates readiness and
   transitions `planned` → `queued`.
6. Update issue status on every issue in `session.yaml.issues`:
   - `ready` → `in_progress`
   - Add a comment on each issue pointing at the session (use
     `comment_templates/status_change.yaml.j2`).
7. Write a launch comment in
   `sessions/$ARGUMENTS/comments/001-queued-<YYYY-MM-DD>.yaml` using
   `comment_templates/status_change.yaml.j2`. Body: one paragraph
   summarising the handoff — reference `handoff.yaml.branch`, the
   agent type, and any open questions.
8. Run `keel validate --strict`. Fix any errors.
9. Commit: `queue: $ARGUMENTS → <agent-type>`.
10. Report the branch name (from `handoff.yaml.branch`) so the user
    can dispatch the execution agent or run `/pm-session-spawn`.

Do NOT create `task-checklist.md`, `recommended-testing-plan.md`, or
`post-completion-comments.md`. Per `templates/artifacts/manifest.yaml`
these are owned by `execution-agent` and created during implementing /
completion phases.

Do NOT create the session itself. If it doesn't exist, tell the user
to run `/pm-session-create <issue-key>` first.
```

- [ ] **Step 2: Delete old pm-session-launch.md**

```bash
git rm src/keel/templates/commands/pm-session-launch.md
```

- [ ] **Step 3: Create pm-session-spawn.md**

```markdown
---
name: pm-session-spawn
description: Spawn a queued session locally via Claude Code subprocess.
argument-hint: "<session-id>"
---

You are the project manager. Load the project-manager skill if not
active.

Session to spawn:
$ARGUMENTS

Workflow:

1. Verify session exists and status is `queued`.
2. Run `keel session spawn $ARGUMENTS --dry-run` to preview the
   spawn (worktree paths, branch, max turns).
3. If dry-run passes, write a launch comment on each issue in
   `session.yaml.issues` (use `comment_templates/status_change.yaml.j2`).
   Body: "Session $ARGUMENTS spawned locally; branch <branch>".
4. Run `keel validate --strict`.
5. Commit: `spawn: $ARGUMENTS (local)`.
6. Run `keel session spawn $ARGUMENTS` (real spawn).
7. Report:
   - Session id, branch, worktree path
   - Log path and PID
   - `tail -f <log-path>` instructions
```

- [ ] **Step 4: Create pm-session-agenda.md**

```markdown
---
name: pm-session-agenda
description: Session-axis agenda with launch recommendations.
argument-hint: ""
---

You are the project manager. Load the project-manager skill if not
active.

Workflow:

1. Run `keel session agenda --format json`.
2. Summarise:
   - Session counts by status
   - Critical path
   - Top 3 launch recommendations with rationale
   - Any warnings (orphan blockers, stale sessions)
3. Reference specific session ids in your summary.
4. End with the literal commands to run next (e.g.
   `/pm-session-queue <id>` or `/pm-session-spawn <id>`).
```

- [ ] **Step 5: Update SKILL.md command table**

In `src/keel/templates/skills/project-manager/SKILL.md`, find the command table and:
- Replace `pm-session-launch` with `pm-session-queue`
- Add `pm-session-spawn`
- Add `pm-session-agenda`

- [ ] **Step 6: Run full suite**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add src/keel/templates/commands/ src/keel/templates/skills/project-manager/SKILL.md
git commit -m "feat: rename pm-session-launch to pm-session-queue, add spawn + agenda slash commands"
```

---

### Task 12: Update docs and references

Update remaining references to the old command names and add the new error codes to VALIDATION.md.

**Files:**
- Modify: `src/keel/templates/skills/project-manager/references/VALIDATION.md`
- Modify: `src/keel/templates/skills/project-manager/references/SCHEMA_SESSIONS.md`
- Modify: `src/keel/cli/session.py` (update docstring)

- [ ] **Step 1: Update session.py docstring**

Replace the module docstring at the top of `src/keel/cli/session.py`:

```python
"""`keel session` — session lifecycle and agenda operations.

Sessions live at `sessions/<id>/session.yaml`.

Subcommands:
- `list` — enumerate all sessions with status and issue counts
- `show <id>` — print one session's full YAML frontmatter + body
- `check <id>` — readiness punch list
- `queue <id>` — validate readiness, transition to queued
- `spawn <id>` — create worktree, launch claude -p, transition to executing
- `pause <id>` — SIGTERM the claude process, transition to paused
- `abandon <id>` — kill if running, transition to abandoned
- `cleanup [<id>]` — remove worktrees for completed/abandoned sessions
- `agenda` — session dependency DAG with launch recommendations
- `progress` — task-checklist rollup across active sessions
- `derive-branch <id>` — print canonical branch name
- `artifacts <id>` — alias for `keel artifacts list <id>`
"""
```

- [ ] **Step 2: Add error codes to VALIDATION.md**

Append the spawn/pause/abandon/cleanup/agenda error codes from spec §9 to the error code table in `src/keel/templates/skills/project-manager/references/VALIDATION.md`.

- [ ] **Step 3: Update SCHEMA_SESSIONS.md**

Add the new `runtime_state` fields (worktrees, pid, started_at, log_path) and the new statuses (queued, executing, paused, abandoned) to the session schema reference.

- [ ] **Step 4: Update handoff.yaml fix_hint**

In `src/keel/core/session_readiness.py`, update the handoff missing fix_hint from "Run /pm-session-launch" to "Run /pm-session-queue".

- [ ] **Step 5: Grep for remaining "pm-session-launch" references**

Run: `cd /Users/maia/Code/seido/projects/keel && grep -r "pm-session-launch" src/ tests/ --include="*.py" --include="*.md" --include="*.yaml"`
Fix any remaining references.

- [ ] **Step 6: Run full suite**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "docs: update session references for new commands and statuses"
```

---

### Task 13: Integration test — full spawn lifecycle

End-to-end test with a claude shim.

**Files:**
- Create: `tests/integration/test_session_spawn_lifecycle.py`

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_session_spawn_lifecycle.py`:

```python
"""Integration test: full session spawn lifecycle with claude shim."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from click.testing import CliRunner

from keel.cli.session import session_cmd
from keel.core.session_store import load_session


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=path, check=True,
    )


def _create_claude_shim(tmp_path: Path) -> Path:
    """Create a fake claude script that sleeps briefly and exits 0."""
    shim = tmp_path / "claude"
    shim.write_text(textwrap.dedent(f"""\
        #!{sys.executable}
        import time, sys
        time.sleep(2)
        sys.exit(0)
    """))
    shim.chmod(0o755)
    return shim


class TestSpawnLifecycle:
    def test_queue_spawn_pause_cleanup(self, tmp_path, tmp_path_project,
                                        save_test_session, write_handoff_yaml):
        """Full lifecycle: queue → spawn → pause → cleanup."""
        # Set up clone repo
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        # Create claude shim
        shim = _create_claude_shim(tmp_path)
        env = {**os.environ, "PATH": f"{tmp_path}:{os.environ.get('PATH', '')}"}

        # Create session
        save_test_session(
            tmp_path_project, "lifecycle-test", plan=True, status="planned",
            repos=[{"repo": "SeidoAI/test", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "lifecycle-test", branch="feat/lifecycle-test")

        runner = CliRunner(env=env)
        pdir = str(tmp_path_project)

        # Queue
        result = runner.invoke(session_cmd, ["queue", "lifecycle-test", "--project-dir", pdir])
        assert result.exit_code == 0, result.output
        assert load_session(tmp_path_project, "lifecycle-test").status == "queued"

        # Spawn (with mocked clone resolution)
        from unittest.mock import patch
        with patch("keel.cli.session._resolve_clone_path", return_value=clone):
            result = runner.invoke(session_cmd, ["spawn", "lifecycle-test", "--project-dir", pdir])

        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "lifecycle-test")
        assert s.status == "executing"
        assert s.runtime_state.pid is not None
        assert len(s.runtime_state.worktrees) == 1

        # Wait briefly for the shim to start
        import time
        time.sleep(0.5)

        # Pause
        result = runner.invoke(session_cmd, ["pause", "lifecycle-test", "--project-dir", pdir])
        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "lifecycle-test")
        assert s.status in ("paused", "failed")  # failed if process already exited

        # Cleanup
        s.status = "completed"  # force to completed for cleanup test
        from keel.core.session_store import save_session
        save_session(tmp_path_project, s)

        result = runner.invoke(session_cmd, ["cleanup", "--project-dir", pdir])
        assert result.exit_code == 0, result.output

    def test_agenda_with_dependencies(self, tmp_path_project, save_test_session):
        """Agenda correctly identifies launchable vs blocked."""
        save_test_session(tmp_path_project, "s1", status="planned")
        save_test_session(tmp_path_project, "s2", status="planned", blocked_by_sessions=["s1"])
        save_test_session(tmp_path_project, "s3", status="completed")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert "LAUNCHABLE" in result.output
        assert "s1" in result.output
        assert "BLOCKED" in result.output
        assert "s2" in result.output
```

- [ ] **Step 2: Run integration test**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/integration/test_session_spawn_lifecycle.py -v`
Expected: PASS

- [ ] **Step 3: Run complete test suite**

Run: `cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/ -x -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_session_spawn_lifecycle.py
git commit -m "test: add integration test for full session spawn lifecycle"
```

---

### Task 14: Final verification

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/maia/Code/seido/projects/keel && uv run pytest tests/ -v 2>&1 | tail -5
```
Expected: All pass, 0 failures

- [ ] **Step 2: Lint check**

```bash
cd /Users/maia/Code/seido/projects/keel && uv run ruff check && uv run ruff format --check
```

- [ ] **Step 3: Verify no stale pm-session-launch references**

```bash
cd /Users/maia/Code/seido/projects/keel && grep -r "pm-session-launch" src/ tests/ --include="*.py" --include="*.md" --include="*.yaml" --include="*.j2"
```
Expected: Zero matches

- [ ] **Step 4: Verify keel validate on test projects**

```bash
cd /Users/maia/Code/seido/projects/project-graph-ui-v2 && uv run --project ~/Code/seido/projects/keel keel validate --strict
```

- [ ] **Step 5: Verify new CLI commands are registered**

```bash
cd /Users/maia/Code/seido/projects/keel && uv run keel session --help
```
Expected: queue, spawn, pause, abandon, cleanup, agenda all listed
