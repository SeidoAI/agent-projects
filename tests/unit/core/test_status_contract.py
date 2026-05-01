"""Unit tests for tripwire.core.status_contract (v0.9.4)."""

from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.core.status_contract import (
    ALLOWED_ISSUE_STATES_BY_SESSION_STATE,
    ISSUE_ALIASES,
    SWEEP_TARGETS,
    is_issue_state_compatible_with_session_state,
    normalize_issue_status,
    normalize_session_status,
    sweep_issues,
    sweep_target_for,
)

# --- Alias maps --------------------------------------------------------------


def test_issue_aliases_cover_all_legacy_names() -> None:
    assert ISSUE_ALIASES == {
        "backlog": "planned",
        "todo": "queued",
        "in_progress": "executing",
        "done": "completed",
        "canceled": "abandoned",
    }


def test_normalize_issue_status_passes_canonical_through() -> None:
    for canonical in (
        "planned",
        "queued",
        "executing",
        "in_review",
        "verified",
        "completed",
        "abandoned",
        "deferred",
    ):
        assert normalize_issue_status(canonical) == canonical


def test_normalize_issue_status_rewrites_legacy() -> None:
    assert normalize_issue_status("backlog") == "planned"
    assert normalize_issue_status("todo") == "queued"
    assert normalize_issue_status("in_progress") == "executing"
    assert normalize_issue_status("done") == "completed"
    assert normalize_issue_status("canceled") == "abandoned"


def test_normalize_session_status_collapses_dead_states() -> None:
    # Dead session states aspirationally added in v0.7 but never written
    # into the transition table — collapse to executing/in_review on read.
    assert normalize_session_status("active") == "executing"
    assert normalize_session_status("waiting_for_ci") == "executing"
    assert normalize_session_status("waiting_for_review") == "in_review"
    assert normalize_session_status("waiting_for_deploy") == "executing"
    assert normalize_session_status("re_engaged") == "executing"


def test_normalize_session_status_passes_canonical_through() -> None:
    for canonical in (
        "planned",
        "queued",
        "executing",
        "in_review",
        "verified",
        "completed",
        "paused",
        "failed",
        "abandoned",
    ):
        assert normalize_session_status(canonical) == canonical


# --- Contract: allowed issue-states-per-session-state -----------------------


def test_planned_session_only_accepts_planned_or_deferred_issues() -> None:
    allowed = ALLOWED_ISSUE_STATES_BY_SESSION_STATE["planned"]
    # v0.9.4 (codex P1 round-4): abandoned is always allowed too —
    # mirrors the project.yaml transition table that lets users drop an
    # issue at any time.
    assert allowed == frozenset({"planned", "deferred", "abandoned"})


def test_queued_session_accepts_planned_through_queued() -> None:
    allowed = ALLOWED_ISSUE_STATES_BY_SESSION_STATE["queued"]
    assert "planned" in allowed
    assert "queued" in allowed
    assert "deferred" in allowed
    assert "executing" not in allowed
    assert "completed" not in allowed


def test_executing_session_accepts_through_in_review() -> None:
    allowed = ALLOWED_ISSUE_STATES_BY_SESSION_STATE["executing"]
    assert "queued" in allowed
    assert "executing" in allowed
    assert "in_review" in allowed
    assert "deferred" in allowed
    # Floor: no member issue may be at planned once session is executing.
    assert "planned" not in allowed
    # Ceiling: not yet completed.
    assert "completed" not in allowed


def test_in_review_session_admits_in_review_verified_deferred_abandoned() -> None:
    # v0.9.4 (codex P1 round-4): verified→in_review session rollback
    # is a documented lifecycle path; the rolled-back session retains
    # already-verified issues. Plus abandoned (always-allowed escape).
    allowed = ALLOWED_ISSUE_STATES_BY_SESSION_STATE["in_review"]
    assert allowed == frozenset(
        {"in_review", "verified", "deferred", "abandoned"}
    )


def test_verified_session_pins_to_verified() -> None:
    allowed = ALLOWED_ISSUE_STATES_BY_SESSION_STATE["verified"]
    assert allowed == frozenset({"verified", "deferred", "abandoned"})


def test_completed_session_accepts_completed_abandoned_deferred() -> None:
    allowed = ALLOWED_ISSUE_STATES_BY_SESSION_STATE["completed"]
    assert "completed" in allowed
    assert "abandoned" in allowed
    assert "deferred" in allowed


def test_paused_failed_abandoned_are_permissive() -> None:
    # Frozen states accept any canonical issue state — issues outlive
    # paused/failed/abandoned sessions and may be at any phase.
    for s in ("paused", "failed", "abandoned"):
        allowed = ALLOWED_ISSUE_STATES_BY_SESSION_STATE[s]
        assert {"planned", "queued", "executing", "completed", "deferred"} <= allowed


# --- Compatibility checks ----------------------------------------------------


def test_compatibility_uses_canonical_via_aliases() -> None:
    # Old name on the issue side, canonical on the session side.
    assert (
        is_issue_state_compatible_with_session_state("executing", "in_progress") is True
    )
    assert is_issue_state_compatible_with_session_state("completed", "done") is True
    assert is_issue_state_compatible_with_session_state("planned", "backlog") is True


def test_floor_violation_rejected() -> None:
    # An issue at "planned" is below the floor of an executing session.
    assert is_issue_state_compatible_with_session_state("executing", "planned") is False


def test_ceiling_violation_rejected() -> None:
    # Issue at completed inside a still-executing session — ceiling
    # violation.
    assert (
        is_issue_state_compatible_with_session_state("executing", "completed") is False
    )


def test_completed_session_rejects_in_progress_issue() -> None:
    assert (
        is_issue_state_compatible_with_session_state("completed", "executing") is False
    )


def test_unknown_session_state_is_permissive() -> None:
    # A session state we don't know about — be lenient. The unknown-state
    # surfaces via a different validator check.
    assert is_issue_state_compatible_with_session_state("UNKNOWN", "planned") is True


# --- Sweep targets -----------------------------------------------------------


def test_sweep_target_for_each_session_state() -> None:
    assert sweep_target_for("planned") is None
    assert sweep_target_for("queued") == "queued"
    assert sweep_target_for("executing") == "queued"
    assert sweep_target_for("in_review") == "in_review"
    assert sweep_target_for("verified") == "verified"
    assert sweep_target_for("completed") == "completed"
    assert sweep_target_for("paused") is None
    assert sweep_target_for("failed") is None
    assert sweep_target_for("abandoned") is None


def test_sweep_target_for_alias_normalizes() -> None:
    # Old session aliases route to a canonical bucket.
    assert sweep_target_for("waiting_for_review") == "in_review"


def test_sweep_targets_keys_match_contract_keys() -> None:
    # Every session state in the contract has an explicit sweep entry.
    assert set(SWEEP_TARGETS) == set(ALLOWED_ISSUE_STATES_BY_SESSION_STATE)


# --- Sweep helper integration -----------------------------------------------


def _write_minimal_project(project_dir: Path) -> None:
    """Build the minimum project structure needed for load_issue / save_issue."""
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "key_prefix": "T",
                "next_issue_number": 100,
                "next_session_number": 100,
                "phase": "executing",
                "created_at": "2026-01-01T00:00:00",
                "labels": [],
                "label_categories": {
                    "executor": ["ai", "human", "mixed"],
                    "verifier": ["required", "optional", "none"],
                    "domain": [],
                    "agent": [],
                },
                "statuses": [
                    "planned",
                    "queued",
                    "executing",
                    "in_review",
                    "verified",
                    "completed",
                    "abandoned",
                    "deferred",
                ],
                "status_transitions": {
                    "planned": ["queued", "abandoned"],
                    "queued": ["executing", "abandoned"],
                    "executing": ["in_review", "abandoned"],
                    "in_review": ["verified", "executing"],
                    "verified": ["completed", "in_review"],
                    "completed": [],
                    "abandoned": [],
                    "deferred": [],
                },
            }
        )
    )
    (project_dir / "issues").mkdir(parents=True, exist_ok=True)
    (project_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (project_dir / "events").mkdir(parents=True, exist_ok=True)
    (project_dir / "graph" / "nodes").mkdir(parents=True, exist_ok=True)


def _make_issue(project_dir: Path, key: str, status: str) -> None:
    issue_dir = project_dir / "issues" / key
    issue_dir.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(
        {
            "uuid": "00000000-0000-4000-8000-{:012x}".format(int(key.split("-")[1])),
            "id": key,
            "title": f"fixture {key}",
            "status": status,
            "priority": "medium",
            "executor": "ai",
            "verifier": "required",
            "labels": [],
            "parent": None,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "created_by": "test",
        }
    )
    (issue_dir / "issue.yaml").write_text(f"---\n{body}---\n")


def _make_fake_session(issue_keys: list[str]):
    """Build a duck-typed session object for sweep_issues without
    materialising a full AgentSession (which has many required fields)."""

    class _FakeSession:
        def __init__(self, keys: list[str]) -> None:
            self.issues = keys

    return _FakeSession(issue_keys)


def test_sweep_issues_advances_only_forward(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    _make_issue(tmp_path, "T-100", "queued")
    _make_issue(tmp_path, "T-101", "executing")
    _make_issue(tmp_path, "T-102", "in_review")
    _make_issue(tmp_path, "T-103", "deferred")
    _make_issue(tmp_path, "T-104", "completed")

    session = _make_fake_session(["T-100", "T-101", "T-102", "T-103", "T-104"])
    changed = sweep_issues(tmp_path, session, "in_review")

    # Issues at queued and executing get advanced to in_review.
    assert set(changed) == {"T-100", "T-101"}

    from tripwire.core.store import load_issue

    assert load_issue(tmp_path, "T-100").status == "in_review"
    assert load_issue(tmp_path, "T-101").status == "in_review"
    # Already at in_review — untouched.
    assert load_issue(tmp_path, "T-102").status == "in_review"
    # Off-path — untouched.
    assert load_issue(tmp_path, "T-103").status == "deferred"
    # Past target — never moved backward.
    assert load_issue(tmp_path, "T-104").status == "completed"


def test_sweep_issues_to_completed_promotes_verified_and_earlier(
    tmp_path: Path,
) -> None:
    _write_minimal_project(tmp_path)
    _make_issue(tmp_path, "T-100", "verified")
    _make_issue(tmp_path, "T-101", "executing")
    _make_issue(tmp_path, "T-102", "abandoned")  # off-path: keep

    session = _make_fake_session(["T-100", "T-101", "T-102"])
    changed = sweep_issues(tmp_path, session, "completed")

    assert set(changed) == {"T-100", "T-101"}

    from tripwire.core.store import load_issue

    assert load_issue(tmp_path, "T-100").status == "completed"
    assert load_issue(tmp_path, "T-101").status == "completed"
    assert load_issue(tmp_path, "T-102").status == "abandoned"


def test_sweep_issues_no_target_for_paused(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    _make_issue(tmp_path, "T-100", "queued")
    session = _make_fake_session(["T-100"])
    changed = sweep_issues(tmp_path, session, "paused")
    assert changed == []
    from tripwire.core.store import load_issue

    assert load_issue(tmp_path, "T-100").status == "queued"


def test_sweep_issues_tolerates_missing_issue_files(tmp_path: Path) -> None:
    _write_minimal_project(tmp_path)
    _make_issue(tmp_path, "T-100", "queued")
    session = _make_fake_session(["T-100", "T-999-MISSING"])
    changed = sweep_issues(tmp_path, session, "in_review")
    assert changed == ["T-100"]


def test_sweep_issues_with_legacy_status_normalizes_then_advances(
    tmp_path: Path,
) -> None:
    _write_minimal_project(tmp_path)
    # Issue saved with the v0.9.3-and-earlier name. The IssueStatus enum's
    # _missing_ alias handler should normalize it on load to "queued".
    # When sweep runs target=in_review, it should advance.
    _make_issue(tmp_path, "T-100", "todo")
    session = _make_fake_session(["T-100"])
    changed = sweep_issues(tmp_path, session, "in_review")
    assert changed == ["T-100"]
    from tripwire.core.store import load_issue

    assert load_issue(tmp_path, "T-100").status == "in_review"


# Run a tiny integration check: ensure ALLOWED contract is consistent with
# the sweep direction. If a session state has a sweep target, that target
# must also be allowed for that session state.
def test_sweep_target_is_in_allowed_set() -> None:
    for session_state, target in SWEEP_TARGETS.items():
        if target is None:
            continue
        allowed = ALLOWED_ISSUE_STATES_BY_SESSION_STATE[session_state]
        assert target in allowed, (
            f"sweep target {target} for session state {session_state} "
            f"is not in the allowed-set {allowed}"
        )
