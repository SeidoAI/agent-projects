"""Watch-daemon harness for the post-PR auto-checks (v0.7.9 §A8).

Wraps :class:`PRWatcher` + :class:`WatcherActionExecutor` in a polling
loop: every ``poll_interval`` seconds, build the list of active
:class:`WatchedSession` records from the project's session-store, run
:meth:`PRWatcher.tick`, and dispatch each emitted action.

State persists between ticks inside the watcher (idempotency
deduplication) and on disk in:

  ``<project>/.tripwire/watch/watch.pid``  — running daemon's PID
  ``<project>/.tripwire/watch/watch.log``  — daemon log (for ``logs --tail``)
  ``<project>/.tripwire/watch/state.json`` — per-session snapshot
                                              (code_pr_opened_at, etc.)

The CLI surface (``tripwire watch start / stop / status / logs``) lives
in :mod:`tripwire.cli.watch`; this module provides the building blocks.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from tripwire.core.pr_watcher import (
    PRWatcher,
    WatchedSession,
)
from tripwire.core.pr_watcher_executor import (
    WatcherActionExecutor,
    fetch_pr_files,
    fetch_pr_state,
)
from tripwire.core.process_helpers import is_alive
from tripwire.core.session_store import list_sessions

logger = logging.getLogger(__name__)


# Statuses the watch daemon polls. Includes inactive ones (in_review,
# verified, completed, done) so the v0.7.10 §B2 post-merge CI failure
# tripwire can re-engage agents whose merge regressed CI on main. The
# other tripwires are guarded by their own conditions (#15 only fires
# on open PRs, #17 only on executing) so widening the set here is safe.
_ACTIVE_STATUSES = {
    "executing",
    "paused",
    "in_review",
    "verified",
    "completed",
    "done",
}


@dataclass
class DaemonConfig:
    project_dir: Path
    poll_interval: float = 300.0  # 5 min default per spec
    token: str | None = None


def watch_dir(project_dir: Path) -> Path:
    return project_dir / ".tripwire" / "watch"


def pidfile_path(project_dir: Path) -> Path:
    return watch_dir(project_dir) / "watch.pid"


def logfile_path(project_dir: Path) -> Path:
    return watch_dir(project_dir) / "watch.log"


def statefile_path(project_dir: Path) -> Path:
    return watch_dir(project_dir) / "state.json"


def write_pidfile(project_dir: Path, pid: int) -> None:
    pid_path = pidfile_path(project_dir)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(pid))


def remove_pidfile(project_dir: Path) -> None:
    try:
        pidfile_path(project_dir).unlink()
    except FileNotFoundError:
        pass


def is_daemon_running(project_dir: Path) -> bool:
    pid_path = pidfile_path(project_dir)
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError):
        return False
    return is_alive(pid)


# ---------- Watched-session derivation -----------------------------------


def _project_repo_slug(project_dir: Path) -> str | None:
    """Best-effort GitHub slug for the project-tracking repo.

    Reads ``origin`` from the project_dir's git config and parses the
    URL into ``owner/repo``. Returns None if the directory isn't a
    git repo or origin isn't a GitHub URL.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(project_dir), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    # Parse git@github.com:owner/repo.git or https://github.com/owner/repo(.git)
    for prefix in ("git@github.com:", "https://github.com/", "ssh://git@github.com/"):
        if url.startswith(prefix):
            tail = url[len(prefix) :]
            if tail.endswith(".git"):
                tail = tail[:-4]
            if "/" in tail:
                return tail
    return None


def _load_artifact_manifest(project_dir: Path) -> list[str]:
    """Return the project-level required-session-artifact names."""
    project_yaml = project_dir / "project.yaml"
    if not project_yaml.exists():
        return []
    try:
        data = yaml.safe_load(project_yaml.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    manifest = data.get("artifact_manifest") or {}
    return list(manifest.get("session_required") or [])


def _load_state(project_dir: Path) -> dict[str, dict]:
    sf = statefile_path(project_dir)
    if not sf.exists():
        return {}
    try:
        return json.loads(sf.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_state(project_dir: Path, state: dict[str, dict]) -> None:
    sf = statefile_path(project_dir)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(state, indent=2), encoding="utf-8")


def build_watched_sessions(project_dir: Path) -> list[WatchedSession]:
    """Walk the project's session-store and build a WatchedSession for
    every active session that has at least one repo.

    Active = ``status in {executing, paused}``. The PT side is
    derived from the project_dir's GitHub remote and the convention
    ``proj/<session_id>``. ``code_pr_opened_at`` is hydrated from
    ``state.json`` if cached, else set to ``now`` so the 10-min
    timer starts on first sighting.
    """
    sessions: list[WatchedSession] = []
    pt_slug = _project_repo_slug(project_dir)
    manifest = _load_artifact_manifest(project_dir)
    state = _load_state(project_dir)
    now = datetime.now(tz=timezone.utc)
    state_dirty = False

    for sess in list_sessions(project_dir):
        if sess.status not in _ACTIVE_STATUSES:
            continue
        if not sess.repos:
            continue
        primary = sess.repos[0]
        sess_state = state.setdefault(sess.id, {})
        opened_at_raw = sess_state.get("code_pr_opened_at")
        if primary.pr_number is not None and opened_at_raw is None:
            sess_state["code_pr_opened_at"] = now.isoformat()
            opened_at_raw = sess_state["code_pr_opened_at"]
            state_dirty = True
        opened_at: datetime | None = None
        if opened_at_raw:
            try:
                opened_at = datetime.fromisoformat(opened_at_raw)
            except ValueError:
                opened_at = None
        sessions.append(
            WatchedSession(
                session_id=sess.id,
                project_dir=project_dir,
                code_repo=primary.repo,
                code_branch=primary.branch or "",
                code_pr_number=primary.pr_number,
                code_pr_opened_at=opened_at,
                pt_repo=pt_slug or "",
                pt_branch=f"proj/{sess.id}",
                pt_pr_number=sess_state.get("pt_pr_number"),
                required_artifacts=[f"sessions/{sess.id}/{name}" for name in manifest],
                session_status=sess.status,
            )
        )
    if state_dirty:
        _save_state(project_dir, state)
    return sessions


# ---------- Daemon --------------------------------------------------------


class WatchDaemon:
    """Loop that ticks the :class:`PRWatcher` against active sessions."""

    def __init__(
        self,
        cfg: DaemonConfig,
        *,
        watcher: PRWatcher | None = None,
        executor: WatcherActionExecutor | None = None,
    ) -> None:
        self.cfg = cfg
        self.watcher = watcher or PRWatcher(
            fetch_pr=fetch_pr_state,
            fetch_pr_files=fetch_pr_files,
            token=cfg.token,
        )
        self.executor = executor or WatcherActionExecutor(
            project_dir=cfg.project_dir, token=cfg.token
        )
        self._stop = threading.Event()

    def tick(self, *, now: datetime | None = None) -> None:
        now = now or datetime.now(tz=timezone.utc)
        try:
            sessions = build_watched_sessions(self.cfg.project_dir)
        except Exception:
            logger.exception("watch: build_watched_sessions failed")
            return
        actions = self.watcher.tick(sessions, now=now)
        for action in actions:
            try:
                self.executor.execute(action)
            except Exception:
                logger.exception("watch: executor failed on %r", action)

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        write_pidfile(self.cfg.project_dir, os.getpid())
        try:
            while not self._stop.is_set():
                self.tick()
                if self._stop.wait(self.cfg.poll_interval):
                    return
        finally:
            remove_pidfile(self.cfg.project_dir)


__all__ = [
    "DaemonConfig",
    "WatchDaemon",
    "build_watched_sessions",
    "is_daemon_running",
    "logfile_path",
    "pidfile_path",
    "remove_pidfile",
    "statefile_path",
    "watch_dir",
    "write_pidfile",
]
