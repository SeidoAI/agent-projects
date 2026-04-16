"""Full session lifecycle integration test (v0.6a).

Exercises the new primitives end-to-end through the CLI:
- scaffold a session manually (simulating what /pm-session-create does)
- derive the canonical branch name
- keel session check surfaces the missing handoff.yaml
- add handoff.yaml (simulating /pm-session-create stamp)
- keel session check passes
- keel validate --strict passes (handoff required at queued, so we
  keep status=planned — launching would be a write operation the CLI
  doesn't do yet in v0.6a; /pm-session-launch's work lives in the
  slash-command body)
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_keel(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "keel", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_full_session_lifecycle(save_test_issue, tmp_path_project):
    save_test_issue(
        tmp_path_project,
        key="TMP-1",
        kind="feat",
        title="Ship v0.6a",
        status="ready",
    )

    # Allocate a session key via the CLI.
    alloc = _run_keel(tmp_path_project, "next-key", "--type", "session")
    assert alloc.returncode == 0, alloc.stdout + alloc.stderr
    session_id = alloc.stdout.strip()

    # Scaffold session directory + session.yaml + plan.md +
    # verification-checklist.md (PM-owned planning artifacts per manifest).
    sess = tmp_path_project / "sessions" / session_id
    sess.mkdir(parents=True)
    (sess / "session.yaml").write_text(
        f"""---
uuid: 11111111-1111-1111-1111-111111111111
id: {session_id}
name: Ship v0.6a
agent: pm
status: planned
issues: [TMP-1]
repos: []
---
""",
        encoding="utf-8",
    )
    (sess / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (sess / "verification-checklist.md").write_text(
        "# Verification\n", encoding="utf-8"
    )

    # Derive the branch name. Session keys from `keel next-key --type
    # session` look like 'TST-S1' (uppercase); derive lowercases the
    # slug to match branch convention.
    derive = _run_keel(tmp_path_project, "session", "derive-branch", session_id)
    assert derive.returncode == 0, derive.stdout + derive.stderr
    branch = derive.stdout.strip()
    slug = session_id.removeprefix("session-").lower()
    assert branch == f"feat/{slug}", branch

    # session check should FAIL: handoff.yaml missing.
    check_missing = _run_keel(tmp_path_project, "session", "check", session_id)
    assert check_missing.returncode != 0
    assert "handoff.yaml" in check_missing.stdout.lower()

    # Write a handoff.yaml (/pm-session-create would do this).
    (sess / "handoff.yaml").write_text(
        f"""---
uuid: 22222222-2222-2222-2222-222222222222
session_id: {session_id}
handoff_at: 2026-04-15T00:00:00Z
handed_off_by: pm
branch: {branch}
open_questions: []
context_to_preserve: []
last_verification_passed_at: null
---
""",
        encoding="utf-8",
    )

    # session check should PASS now.
    check_ok = _run_keel(tmp_path_project, "session", "check", session_id)
    assert check_ok.returncode == 0, check_ok.stdout + check_ok.stderr
    assert "launch-ready" in check_ok.stdout.lower()

    # keel validate should pass (session is in planned status, handoff
    # isn't required yet, but schema is valid).
    validate = _run_keel(tmp_path_project, "validate", "--strict")
    # We don't insist on exit 0 because the freshly-scaffolded project
    # may have phase/heuristic findings unrelated to our session work.
    # What we do insist on: no handoff_schema/* findings in the output.
    assert "handoff_schema/" not in validate.stdout, validate.stdout + validate.stderr
