"""PM-review workflow status (KUI-150).

Drives ``run_pm_review`` against a fixture project and asserts:

- the 10 named checks each produce one entry on the verdict;
- the verdict is ``auto-merge`` when every check passes;
- the verdict is ``request_changes`` when any check fails;
- the ``sessions/<sid>/artifacts/pm-review.md`` artifact is written;
- a ``pm_review.completed`` event is emitted with the outcome.

The 10 checks are literal validator re-runs (see decisions.md D1) — the
runner shells out to :func:`validate_project` and partitions the report
by validator id rather than re-implementing each check.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest


def _scaffold_project(tmp_path: Path) -> Path:
    """Init a minimal project + a session directory ready for pm-review."""
    (tmp_path / "project.yaml").write_text(
        "name: test\nkey_prefix: TST\nbase_branch: main\n"
        "statuses: [planned, queued, executing, in_review, verified, completed]\n"
        "status_transitions:\n"
        "  planned: [queued]\n"
        "  queued: [executing]\n"
        "  executing: [in_review]\n"
        "  in_review: [verified]\n"
        "  verified: [completed]\n"
        "  completed: []\n"
        "repos: {}\nnext_issue_number: 1\nnext_session_number: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "workflow.yaml").write_text(
        dedent(
            """\
            workflows:
              coding-session:
                actor: coding-agent
                trigger: session.spawn
                statuses:
                  - id: planned
                    next: queued
                  - id: queued
                    next: executing
                  - id: executing
                    next: in_review
                  - id: in_review
                    next: verified
                  - id: verified
                    next: completed
                  - id: completed
                    terminal: true
              pm-review:
                actor: pm-agent
                trigger: session.handover
                statuses:
                  - id: review
                    next:
                      - if: pm_review.outcome == auto-merge
                        then: auto_merge
                      - if: pm_review.outcome == request_changes
                        then: request_changes
                      - else: re_engage
                  - id: auto_merge
                    terminal: true
                  - id: request_changes
                    terminal: true
                  - id: re_engage
                    terminal: true
            """
        ),
        encoding="utf-8",
    )
    sdir = tmp_path / "sessions" / "pm-review-target"
    sdir.mkdir(parents=True)
    (sdir / "session.yaml").write_text(
        "---\n"
        "uuid: 11111111-1111-4111-8111-111111111111\n"
        "id: pm-review-target\n"
        "name: PM review target\n"
        "agent: backend-coder\n"
        "issues: []\n"
        "repos: []\n"
        "status: in_review\n"
        "created_at: 2026-04-30T00:00:00Z\n"
        "updated_at: 2026-04-30T00:00:00Z\n"
        "---\n",
        encoding="utf-8",
    )
    (sdir / "artifacts").mkdir()
    return tmp_path


@pytest.fixture
def clean_validator(monkeypatch):
    """Patch validate_project to return a clean report."""
    from tripwire.core.validator._types import ValidationReport

    def _clean(*args, **kwargs):
        return ValidationReport(exit_code=0, errors=[], warnings=[])

    monkeypatch.setattr("tripwire.core.pm_review.runner.validate_project", _clean)
    return _clean


@pytest.fixture
def failing_validator(monkeypatch):
    """Patch validate_project to return one schema error per call."""
    from tripwire.core.validator._types import CheckResult, ValidationReport

    def _bad(*args, **kwargs):
        return ValidationReport(
            exit_code=2,
            errors=[
                CheckResult(
                    code="schema/uuid_missing",
                    severity="error",
                    file="issues/TST-1/issue.yaml",
                    message="uuid missing",
                ),
                CheckResult(
                    code="refs/unresolved",
                    severity="error",
                    file="issues/TST-1/issue.yaml",
                    message="reference [[node-x]] does not resolve",
                ),
            ],
            warnings=[],
        )

    monkeypatch.setattr("tripwire.core.pm_review.runner.validate_project", _bad)
    return _bad


def test_run_pm_review_clean_yields_auto_merge(tmp_path, clean_validator):
    """Every check passes → verdict is `auto-merge`."""
    from tripwire.core.pm_review import run_pm_review

    pd = _scaffold_project(tmp_path)
    verdict = run_pm_review(pd, session_id="pm-review-target")

    assert verdict.verdict == "auto-merge", verdict
    assert verdict.session_id == "pm-review-target"
    # Plan calls out 10 checks.
    assert len(verdict.checks) == 10, [c.name for c in verdict.checks]
    # Every check passed.
    assert all(c.outcome == "pass" for c in verdict.checks)


def test_run_pm_review_failing_yields_request_changes(tmp_path, failing_validator):
    """Validator-fail → verdict is `request_changes` with affected checks."""
    from tripwire.core.pm_review import run_pm_review

    pd = _scaffold_project(tmp_path)
    verdict = run_pm_review(pd, session_id="pm-review-target")

    assert verdict.verdict == "request_changes", verdict
    failed = [c for c in verdict.checks if c.outcome == "fail"]
    failed_names = sorted(c.name for c in failed)
    # `schema/...` finding routes to `schema`; `refs/...` routes to `refs`.
    assert "schema" in failed_names
    assert "refs" in failed_names


def test_run_pm_review_writes_artifact(tmp_path, clean_validator):
    """Writes ``sessions/<sid>/artifacts/pm-review.md`` per the plan."""
    from tripwire.core.pm_review import run_pm_review

    pd = _scaffold_project(tmp_path)
    verdict = run_pm_review(pd, session_id="pm-review-target")

    artifact = pd / "sessions" / "pm-review-target" / "artifacts" / "pm-review.md"
    assert artifact.is_file()
    assert verdict.artifact_path == artifact
    text = artifact.read_text(encoding="utf-8")
    assert "auto-merge" in text
    # Each check name appears in the artifact body so a reader can scan
    # the verdict per-check.
    for name in (
        "schema",
        "refs",
        "status_transition",
        "fields",
        "markdown_structure",
        "freshness",
        "artifact_presence",
        "no_orphan_additions",
        "comment_provenance",
        "project_standards",
    ):
        assert name in text, f"check {name!r} missing from artifact"


def test_run_pm_review_emits_completed_event(tmp_path, clean_validator):
    """Emits a ``pm_review.completed`` event with outcome details."""
    from tripwire.core.events.log import read_events
    from tripwire.core.pm_review import run_pm_review

    pd = _scaffold_project(tmp_path)
    run_pm_review(pd, session_id="pm-review-target")

    events = list(
        read_events(
            pd,
            workflow="pm-review",
            instance="pm-review-target",
            event="pm_review.completed",
        )
    )
    assert len(events) == 1
    assert events[0]["details"]["outcome"] == "auto-merge"


def test_run_pm_review_failing_event_has_failed_checks(tmp_path, failing_validator):
    """The completed event details enumerate each failed check name."""
    from tripwire.core.events.log import read_events
    from tripwire.core.pm_review import run_pm_review

    pd = _scaffold_project(tmp_path)
    run_pm_review(pd, session_id="pm-review-target")

    events = list(
        read_events(
            pd,
            workflow="pm-review",
            instance="pm-review-target",
            event="pm_review.completed",
        )
    )
    assert len(events) == 1
    failed_names = events[0]["details"].get("failed_checks") or []
    assert "schema" in failed_names
    assert "refs" in failed_names


def test_run_pm_review_unknown_session_raises(tmp_path, clean_validator):
    """Calling with a session id that doesn't exist raises FileNotFoundError."""
    from tripwire.core.pm_review import run_pm_review

    pd = _scaffold_project(tmp_path)
    with pytest.raises(FileNotFoundError):
        run_pm_review(pd, session_id="does-not-exist")


def test_run_pm_review_passes_session_id_to_validator(monkeypatch, tmp_path):
    """Codex P2: ``validate_project`` is called with the reviewed
    session id, not the CLI sentinel. Otherwise the
    ``validator.run`` workflow events emitted during the review get
    attributed to ``_cli_validate`` and skew ``/workflow-stats``.
    """
    from tripwire.core.pm_review import run_pm_review
    from tripwire.core.validator._types import ValidationReport

    captured: dict[str, object] = {}

    def _spy(*args, **kwargs):
        captured["session_id"] = kwargs.get("session_id")
        captured["strict"] = kwargs.get("strict")
        return ValidationReport(exit_code=0, errors=[], warnings=[])

    monkeypatch.setattr("tripwire.core.pm_review.runner.validate_project", _spy)

    pd = _scaffold_project(tmp_path)
    run_pm_review(pd, session_id="pm-review-target")

    assert captured["session_id"] == "pm-review-target"
    assert captured["strict"] is True
