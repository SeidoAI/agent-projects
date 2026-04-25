"""End-to-end coverage of the v0.7.9 runtime monitors.

Two specific test scenarios pinned to the failure modes the release
exists to fix:

  * #12 — cost overrun (the v0.7.5 $221 fix). A real subprocess is
    spawned; the monitor runner is wired against it; a stream-json
    log is appended that blows the budget; the runner is expected to
    SIGTERM the subprocess, transition status to paused, and inject
    a PM follow-up into plan.md.

  * #15 — code PR open, PT PR missing 10 min later (the 2026-04-25
    3-of-6 fix). Mock GH responses are wired; the watcher tick at
    t=now+11m is expected to inject the follow-up, kick a re-engage,
    and not re-fire on the next tick.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def project(tmp_path: Path, save_test_session) -> Path:
    (tmp_path / "project.yaml").write_text(
        "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\n"
        "next_session_number: 1\nrepos:\n  SeidoAI/code:\n"
        "    local: /tmp/code\nartifact_manifest:\n"
        "  session_required: [self-review.md, insights.yaml]\n"
        "  issue_required: [developer.md]\n"
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    save_test_session(tmp_path, "s1", plan=True, status="executing")
    return tmp_path


def test_cost_overrun_e2e_sigterms_real_subprocess_and_pauses_session(
    project: Path, tmp_path: Path
):
    """The v0.7.5-$221 failure mode end-to-end.

    A real long-running subprocess is launched. The monitor runner
    polls it; we append a budget-busting stream-json event to the
    log file. The runner must:

      1. Detect the cost overrun
      2. SIGTERM the subprocess (proving the budget cap is enforced)
      3. Transition session.status to 'paused' on disk
      4. Inject the cost-overrun follow-up into plan.md
    """
    from tripwire.core.session_store import load_session
    from tripwire.runtimes.monitor_runner import MonitorRunner, RunnerConfig

    log_path = tmp_path / "agent.log"
    log_path.write_text("")
    monitor_log = tmp_path / "monitor.log"

    # Long-running placeholder for the agent. The python -u -c is
    # cross-platform and won't accidentally exit early.
    proc = subprocess.Popen(
        [sys.executable, "-u", "-c", "import time\nwhile True: time.sleep(0.1)"],
    )
    try:
        cfg = RunnerConfig(
            session_id="s1",
            pid=proc.pid,
            log_path=log_path,
            code_worktree=tmp_path / "code",
            pt_worktree=None,
            project_dir=project,
            max_budget_usd=0.0001,  # vanishingly small, blown by one event
            monitor_log_path=monitor_log,
            poll_interval=0.05,
        )

        runner = MonitorRunner(cfg, max_runtime_seconds=10.0)
        runner_thread = threading.Thread(target=runner.run, daemon=True)
        runner_thread.start()

        # Give the monitor a beat to start tailing, then append a
        # budget-busting usage event.
        time.sleep(0.2)
        with log_path.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "model": "claude-opus-4-7",
                            "usage": {
                                "input_tokens": 10_000,
                                "output_tokens": 10_000,
                            },
                        },
                    }
                )
                + "\n"
            )
            f.flush()

        # Wait for the subprocess to die (proves SIGTERM landed) +
        # for the runner to flush its on-exit hooks.
        proc.wait(timeout=10)
        runner_thread.join(timeout=5)

        # 1. SIGTERM was sent → process exited.
        assert proc.poll() is not None, "agent subprocess should have been SIGTERMed"
        # 2. Status flipped to paused.
        session = load_session(project, "s1")
        assert session.status == "paused"
        # 3. plan.md has the follow-up block.
        plan_text = (project / "sessions" / "s1" / "plan.md").read_text()
        assert "cost overrun" in plan_text.lower()
        assert "monitor:tripwire=monitor/cost_overrun" in plan_text
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)


def test_post_pr_watcher_e2e_reengages_on_missing_pt_pr_after_10_min(
    project: Path, save_test_session
):
    """The 2026-04-25 3-of-6 failure mode end-to-end.

    A session has a code PR open; the matching PT PR doesn't exist.
    The watcher tick at t=now+11min must inject the follow-up into
    plan.md and call the re-engage subprocess. Subsequent ticks must
    not re-fire (idempotency proves the operator isn't spammed).
    """
    save_test_session(
        project,
        "s_active",
        plan=True,
        status="executing",
        repos=[
            {
                "repo": "SeidoAI/code",
                "base_branch": "main",
                "branch": "feat/s_active",
                "pr_number": 42,
            }
        ],
    )
    # Plan.md must already exist for the inject to land. The fixture
    # writes a one-line stub.
    plan_path = project / "sessions" / "s_active" / "plan.md"

    from tripwire.core.pr_watcher import PRState
    from tripwire.core.pr_watcher_daemon import (
        DaemonConfig,
        WatchDaemon,
        statefile_path,
    )

    fetch_pr_calls: list[tuple] = []

    def fake_fetch_pr(repo, pr_number, token=None):
        fetch_pr_calls.append((repo, pr_number))
        return PRState(
            number=pr_number, state="open", merged=False, head_branch="feat/s_active"
        )

    def fake_fetch_files(repo, pr_number, token=None):
        return []

    cfg = DaemonConfig(project_dir=project, poll_interval=0.05, token=None)
    daemon = WatchDaemon(cfg)
    # Replace the watcher's fetchers with the fake ones, but keep
    # the real executor wired so we exercise plan.md injection.
    from tripwire.core.pr_watcher import PRWatcher

    daemon.watcher = PRWatcher(
        fetch_pr=fake_fetch_pr,
        fetch_pr_files=fake_fetch_files,
        token=None,
    )

    with (
        patch(
            "tripwire.core.pr_watcher_daemon._project_repo_slug",
            return_value="SeidoAI/tripwire-v0",
        ),
        patch("tripwire.core.pr_watcher_executor.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        # First tick: bootstraps state.json with code_pr_opened_at = now.
        daemon.tick(now=datetime.now(tz=timezone.utc))
        # Second tick: 11 min later — the no-PT-PR tripwire fires.
        future = datetime.now(tz=timezone.utc) + timedelta(minutes=11)
        # Forge state.json so the elapsed timer crosses the 10-min mark.
        sf = statefile_path(project)
        cached = json.loads(sf.read_text())
        cached["s_active"]["code_pr_opened_at"] = (
            future - timedelta(minutes=11)
        ).isoformat()
        sf.write_text(json.dumps(cached, indent=2))
        daemon.tick(now=future)
        # Third tick at the same time: idempotent — no re-fire.
        daemon.tick(now=future)

    # The inject landed.
    text = plan_path.read_text()
    assert "code PR opened, project-tracking PR missing" in text
    assert text.count("watcher:tripwire=watcher/code_pr_no_pt_pr") == 1
    # The re-engage was called: we expect at least one pause + one spawn.
    invocations = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    assert any("session pause s_active" in c for c in invocations)
    assert any("session spawn s_active" in c and "--resume" in c for c in invocations)
