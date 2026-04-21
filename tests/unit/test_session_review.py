"""Session review pure functions."""

from tripwire.core.session_review import (
    ReviewReport,
    check_plan_adherence,
    check_stop_and_ask,
    detect_deviations,
    parse_acceptance_criteria,
    parse_repo_scope,
)


def test_parse_acceptance_criteria():
    body = """
## Acceptance criteria
- [ ] Users can log in with email
- [ ] Auth token expires after 15 minutes
- [x] Refresh token rotates on suspicious IP change

## Test plan
"""
    criteria = parse_acceptance_criteria(body)
    assert len(criteria) == 3
    assert "email" in criteria[0]
    assert "Refresh token" in criteria[2]


def test_parse_acceptance_criteria_no_section():
    assert parse_acceptance_criteria("# Just a title\n\nSome text.") == []


def test_parse_repo_scope():
    body = """
## Repo scope
- src/auth/
- src/lib/utils.py

## Requirements
"""
    scope = parse_repo_scope(body)
    assert scope == ["src/auth/", "src/lib/utils.py"]


def test_detect_deviations_flags_out_of_scope():
    pr_files = ["src/auth/jwt.py", "src/payments/stripe.py", "src/auth/roles.py"]
    scope_paths = ["src/auth/"]
    devs = detect_deviations(pr_files, scope_paths)
    assert devs["unspec_files"] == ["src/payments/stripe.py"]


def test_detect_deviations_empty_scope_flags_everything():
    pr_files = ["a.py", "b.py"]
    devs = detect_deviations(pr_files, [])
    assert set(devs["unspec_files"]) == {"a.py", "b.py"}


def test_check_plan_adherence_happy():
    plan = "Touch `src/a.py` and `src/b.py`"
    pr_files = ["src/a.py", "src/b.py"]
    ok, unmatched = check_plan_adherence(plan, pr_files)
    assert ok is True
    assert unmatched == []


def test_check_plan_adherence_reports_unmatched():
    plan = "Touch `src/a.py` and `src/missing.py`"
    pr_files = ["src/a.py"]
    ok, unmatched = check_plan_adherence(plan, pr_files)
    assert ok is False
    assert "src/missing.py" in unmatched


def test_check_stop_and_ask_returns_clauses():
    body = "Normal text.\nIf ambiguous, stop and ask the user.\nOther line.\n"
    clauses = check_stop_and_ask(body)
    assert len(clauses) == 1
    assert "stop and ask" in clauses[0]


def test_review_report_exit_codes():
    r = ReviewReport(session_id="s", pr_number=1, verdict="approved")
    assert r.exit_code == 0
    r.verdict = "approved_with_notes"
    assert r.exit_code == 1
    r.verdict = "rejected"
    assert r.exit_code == 2
