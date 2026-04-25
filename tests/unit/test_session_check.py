"""Strict pre-spawn check (§A6) — 8 tripwires that block launch.

Each tripwire has its own fixture-based test that asserts the specific
error code (e.g. ``check/plan_unfilled``). The strict check is the gate
``tripwire session spawn`` runs before mutating the filesystem; if any
``severity="error"`` result fires, spawn refuses with no bypass.

Tests use ``tmp_path_project`` from conftest.py for the project skeleton
and ``save_test_session`` to seed sessions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tripwire.core.session_check import (
    StrictCheckResult,
    strict_check,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_session_artifacts(
    project_dir: Path,
    session_id: str,
    *,
    plan: str = "",
    task_checklist: str = "",
    verification_checklist: str = "",
) -> None:
    """Write filled-in artifacts for a session so each test can isolate
    one tripwire under test from interference by the others."""
    sess_dir = project_dir / "sessions" / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    if plan:
        (sess_dir / "plan.md").write_text(plan, encoding="utf-8")
    if task_checklist:
        (sess_dir / "task-checklist.md").write_text(task_checklist, encoding="utf-8")
    if verification_checklist:
        (sess_dir / "verification-checklist.md").write_text(
            verification_checklist, encoding="utf-8"
        )


_FILLED_PLAN = """# Plan — example

## Goal

This is a real goal description that exceeds two hundred characters in
length so the plan_unfilled heuristic does not fire on body length. The
agent should read this and understand the intent. We're testing the
strict check pipeline end to end.

## Issues in scope

- TMP-1: setup

## Repos

- example/repo

## Approach

### Phase 1: Investigation
Read the codebase.

### Phase 2: Implementation
Build the thing.

### Phase 3: Verification
Run the tests.
"""

_FILLED_CHECKLIST = """# Task Checklist — example

| # | Task | Status | Comments |
|---|------|--------|----------|
| 1 | Investigate | done | already filed for KUI-1 |
| 2 | Implement | in_progress | core path landed |
"""

_FILLED_VERIFICATION = """# Verification Checklist — example

## Acceptance criteria
- [x] Thing one verified — see commit abc123
- [ ] Thing two pending evidence

## Code quality
- [x] Tests pass — pytest output attached
"""


def _seed_filled_session(
    project_dir: Path,
    session_id: str,
    save_test_session,
    save_test_issue,
    *,
    issues: list[str] | None = None,
    repos: list[dict] | None = None,
    spawn_config: dict | None = None,
) -> None:
    """Write a session that passes every tripwire EXCEPT the one being
    tested. Individual tests then override the relevant artifact or
    field to violate exactly one tripwire."""
    issues = issues if issues is not None else ["TMP-1"]
    repos = (
        repos
        if repos is not None
        else [{"repo": "example/code", "base_branch": "main"}]
    )
    for key in issues:
        save_test_issue(project_dir, key=key)
    kwargs: dict = {"issues": issues, "repos": repos}
    if spawn_config is not None:
        kwargs["spawn_config"] = spawn_config
    save_test_session(project_dir, session_id=session_id, **kwargs)
    _write_session_artifacts(
        project_dir,
        session_id,
        plan=_FILLED_PLAN,
        task_checklist=_FILLED_CHECKLIST,
        verification_checklist=_FILLED_VERIFICATION,
    )


# ---------------------------------------------------------------------------
# Skeleton — strict_check returns a list of StrictCheckResult
# ---------------------------------------------------------------------------


class TestSkeleton:
    def test_strict_check_returns_list_of_results(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-skeleton",
            save_test_session,
            save_test_issue,
        )
        results = strict_check(tmp_path_project, "session-skeleton")
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, StrictCheckResult)
            assert r.error_code.startswith("check/")
            assert r.severity in ("error", "warning")

    def test_filled_session_has_no_errors(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-clean",
            save_test_session,
            save_test_issue,
        )
        results = strict_check(tmp_path_project, "session-clean")
        errors = [r for r in results if r.severity == "error"]
        assert errors == [], f"expected no errors, got: {[r.error_code for r in errors]}"


# ---------------------------------------------------------------------------
# Tripwire #1 — check/plan_unfilled
# ---------------------------------------------------------------------------


class TestPlanUnfilled:
    def test_placeholder_syntax_trips(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-plan-placeholder",
            save_test_session,
            save_test_issue,
        )
        # Overwrite plan.md with placeholder content from the scaffold template.
        (tmp_path_project / "sessions" / "session-plan-placeholder" / "plan.md").write_text(
            "# Plan — <session-id>\n\n## Goal\nWhat is this session trying "
            "to achieve, in one paragraph?\n\n## Issues in scope\n- <KEY>: title\n",
            encoding="utf-8",
        )
        results = strict_check(tmp_path_project, "session-plan-placeholder")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/plan_unfilled" in codes

    def test_scaffold_string_trips(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-plan-scaffold-string",
            save_test_session,
            save_test_issue,
        )
        # Even without `<>` placeholders, the literal scaffold-doc string
        # "What to read, what to understand" reveals an unfilled plan.
        (tmp_path_project / "sessions" / "session-plan-scaffold-string" / "plan.md").write_text(
            "# Plan — example\n\n## Goal\n"
            + ("Filler text to push past the 200-character body floor. " * 10)
            + "\n\n## Approach\n\n### Phase 1: Investigation\n"
            "What to read, what to understand, what assumptions to verify.\n",
            encoding="utf-8",
        )
        results = strict_check(tmp_path_project, "session-plan-scaffold-string")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/plan_unfilled" in codes

    def test_short_body_trips(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-plan-short",
            save_test_session,
            save_test_issue,
        )
        (tmp_path_project / "sessions" / "session-plan-short" / "plan.md").write_text(
            "# Plan — example\n\n## Goal\nDo the thing.\n",
            encoding="utf-8",
        )
        results = strict_check(tmp_path_project, "session-plan-short")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/plan_unfilled" in codes

    def test_filled_plan_passes(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-plan-ok",
            save_test_session,
            save_test_issue,
        )
        results = strict_check(tmp_path_project, "session-plan-ok")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/plan_unfilled" not in codes


# ---------------------------------------------------------------------------
# Tripwire #2 — check/checklist_unfilled
# ---------------------------------------------------------------------------


class TestChecklistUnfilled:
    def test_all_pending_no_body_trips(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-checklist-empty",
            save_test_session,
            save_test_issue,
        )
        # Scaffolded task-checklist: every row pending, comments are em-dashes.
        (
            tmp_path_project / "sessions" / "session-checklist-empty" / "task-checklist.md"
        ).write_text(
            "# Task Checklist — example\n\n"
            "| # | Task | Status | Comments |\n"
            "|---|------|--------|----------|\n"
            "| 1 | Investigate | pending | — |\n"
            "| 2 | Implement | pending | — |\n"
            "| 3 | Test | pending | — |\n",
            encoding="utf-8",
        )
        results = strict_check(tmp_path_project, "session-checklist-empty")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/checklist_unfilled" in codes

    def test_pending_with_real_comments_passes(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-checklist-commented",
            save_test_session,
            save_test_issue,
        )
        (
            tmp_path_project / "sessions" / "session-checklist-commented" / "task-checklist.md"
        ).write_text(
            "# Task Checklist — example\n\n"
            "| # | Task | Status | Comments |\n"
            "|---|------|--------|----------|\n"
            "| 1 | Investigate | pending | scoped to module X only |\n"
            "| 2 | Implement | pending | depends on KUI-99 landing |\n",
            encoding="utf-8",
        )
        results = strict_check(tmp_path_project, "session-checklist-commented")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/checklist_unfilled" not in codes


# ---------------------------------------------------------------------------
# Tripwire #3 — check/verification_unfilled
# ---------------------------------------------------------------------------


class TestVerificationUnfilled:
    def test_all_unchecked_no_evidence_trips(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-verif-empty",
            save_test_session,
            save_test_issue,
        )
        (
            tmp_path_project
            / "sessions"
            / "session-verif-empty"
            / "verification-checklist.md"
        ).write_text(
            "# Verification Checklist — example\n\n"
            "## Acceptance criteria\n- [ ] All AC\n\n"
            "## Code quality\n- [ ] Tests pass\n- [ ] Lint passes\n",
            encoding="utf-8",
        )
        results = strict_check(tmp_path_project, "session-verif-empty")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/verification_unfilled" in codes

    def test_evidence_present_passes(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-verif-with-evidence",
            save_test_session,
            save_test_issue,
        )
        # Default _FILLED_VERIFICATION already has evidence; explicit re-seed.
        results = strict_check(tmp_path_project, "session-verif-with-evidence")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/verification_unfilled" not in codes


# ---------------------------------------------------------------------------
# Tripwire #4 — check/repos_overlap (today's bug)
# ---------------------------------------------------------------------------


class TestReposOverlap:
    def test_overlap_with_project_dir_trips(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        # project_dir's name is "proj"; if a session.repo's local clone path
        # resolves to project_dir, that's the overlap bug from 2026-04-25.
        # Project repo points at project_dir itself.
        proj_yaml = tmp_path_project / "project.yaml"
        proj_yaml.write_text(
            "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\n"
            "next_session_number: 1\n"
            "repos:\n"
            f"  same/repo:\n    local: {tmp_path_project}\n",
            encoding="utf-8",
        )
        _seed_filled_session(
            tmp_path_project,
            "session-overlap",
            save_test_session,
            save_test_issue,
            repos=[{"repo": "same/repo", "base_branch": "main"}],
        )
        results = strict_check(tmp_path_project, "session-overlap")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/repos_overlap" in codes

    def test_distinct_repos_pass(
        self, tmp_path_project, save_test_session, save_test_issue, tmp_path
    ):
        other_repo = tmp_path / "other-clone"
        other_repo.mkdir()
        proj_yaml = tmp_path_project / "project.yaml"
        proj_yaml.write_text(
            "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\n"
            "next_session_number: 1\n"
            "repos:\n"
            f"  org/code:\n    local: {other_repo}\n",
            encoding="utf-8",
        )
        _seed_filled_session(
            tmp_path_project,
            "session-no-overlap",
            save_test_session,
            save_test_issue,
            repos=[{"repo": "org/code", "base_branch": "main"}],
        )
        results = strict_check(tmp_path_project, "session-no-overlap")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/repos_overlap" not in codes


# ---------------------------------------------------------------------------
# Tripwire #5 — check/no_repos
# ---------------------------------------------------------------------------


class TestNoRepos:
    def test_empty_repos_trips(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-no-repos",
            save_test_session,
            save_test_issue,
            repos=[],
        )
        results = strict_check(tmp_path_project, "session-no-repos")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/no_repos" in codes


# ---------------------------------------------------------------------------
# Tripwire #6 — check/no_issues
# ---------------------------------------------------------------------------


class TestNoIssues:
    def test_empty_issues_trips(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        # Skip _seed_filled_session's default of one issue.
        save_test_session(
            tmp_path_project,
            session_id="session-no-issues",
            issues=[],
            repos=[{"repo": "example/code", "base_branch": "main"}],
        )
        _write_session_artifacts(
            tmp_path_project,
            "session-no-issues",
            plan=_FILLED_PLAN,
            task_checklist=_FILLED_CHECKLIST,
            verification_checklist=_FILLED_VERIFICATION,
        )
        results = strict_check(tmp_path_project, "session-no-issues")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/no_issues" in codes


# ---------------------------------------------------------------------------
# Tripwire #7 — check/missing_template (warn-only, NOT block)
# ---------------------------------------------------------------------------


class TestMissingTemplate:
    def test_dod_lists_path_with_no_template_warns(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        # Issue DoD references a template file that doesn't exist as a .j2.
        from tripwire.core.store import save_issue
        from tripwire.models import Issue

        body = (
            "## Context\n[[user-model]]\n\n## Implements\nREQ\n\n"
            "## Repo scope\n- example/code\n\n## Requirements\n- thing\n\n"
            "## Execution constraints\nstop and ask\n\n"
            "## Acceptance criteria\n- [ ] thing\n\n"
            "## Test plan\n```\npytest\n```\n\n"
            "## Dependencies\nnone\n\n"
            "## Definition of Done\n- [ ] custom-artifact-no-template.md committed\n"
        )
        issue = Issue.model_validate(
            {
                "id": "TMP-1",
                "title": "Test",
                "status": "todo",
                "priority": "medium",
                "executor": "ai",
                "verifier": "required",
                "kind": "feat",
                "body": body,
            }
        )
        save_issue(tmp_path_project, issue, update_cache=False)
        save_test_session(
            tmp_path_project,
            session_id="session-missing-tpl",
            issues=["TMP-1"],
            repos=[{"repo": "example/code", "base_branch": "main"}],
        )
        _write_session_artifacts(
            tmp_path_project,
            "session-missing-tpl",
            plan=_FILLED_PLAN,
            task_checklist=_FILLED_CHECKLIST,
            verification_checklist=_FILLED_VERIFICATION,
        )
        results = strict_check(tmp_path_project, "session-missing-tpl")
        warnings = [r for r in results if r.severity == "warning"]
        warn_codes = [r.error_code for r in warnings]
        assert "check/missing_template" in warn_codes
        # CRITICAL: warn must NOT block. No `error` of this code.
        error_codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/missing_template" not in error_codes


# ---------------------------------------------------------------------------
# Tripwire #8 — check/invalid_effort
# ---------------------------------------------------------------------------


class TestInvalidEffort:
    def test_xhigh_on_sonnet_trips(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-bad-effort",
            save_test_session,
            save_test_issue,
            spawn_config={"config": {"model": "sonnet", "effort": "xhigh"}},
        )
        results = strict_check(tmp_path_project, "session-bad-effort")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/invalid_effort" in codes

    def test_xhigh_on_opus_passes(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        _seed_filled_session(
            tmp_path_project,
            "session-good-effort",
            save_test_session,
            save_test_issue,
            spawn_config={"config": {"model": "opus", "effort": "xhigh"}},
        )
        results = strict_check(tmp_path_project, "session-good-effort")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/invalid_effort" not in codes

    def test_unknown_model_warns_or_passes(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        # Brand-new model name shouldn't hard-fail on a hardcoded matrix —
        # the matrix is best-effort, and v0.7.10's routing.yaml is what
        # makes it data-driven. Unknown model is treated as "can't validate"
        # and does not fire as an error.
        _seed_filled_session(
            tmp_path_project,
            "session-unknown-model",
            save_test_session,
            save_test_issue,
            spawn_config={"config": {"model": "future-model-x", "effort": "low"}},
        )
        results = strict_check(tmp_path_project, "session-unknown-model")
        codes = [r.error_code for r in results if r.severity == "error"]
        assert "check/invalid_effort" not in codes


# ---------------------------------------------------------------------------
# Cross-tripwire helper: error-code presence implies non-launch
# ---------------------------------------------------------------------------


class TestAggregate:
    def test_any_error_means_not_ready(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        from tripwire.core.session_check import any_blocking_error

        _seed_filled_session(
            tmp_path_project,
            "session-clean-aggregate",
            save_test_session,
            save_test_issue,
        )
        clean = strict_check(tmp_path_project, "session-clean-aggregate")
        assert any_blocking_error(clean) is False

        # Drop plan.md to a placeholder.
        (
            tmp_path_project / "sessions" / "session-clean-aggregate" / "plan.md"
        ).write_text("# <fill>\n", encoding="utf-8")
        dirty = strict_check(tmp_path_project, "session-clean-aggregate")
        assert any_blocking_error(dirty) is True


# ---------------------------------------------------------------------------
# Smoke: missing session
# ---------------------------------------------------------------------------


class TestMissingSession:
    def test_unknown_session_raises_filenotfound(self, tmp_path_project):
        with pytest.raises(FileNotFoundError):
            strict_check(tmp_path_project, "session-does-not-exist")
