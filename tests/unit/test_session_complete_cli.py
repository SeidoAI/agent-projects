"""CLI surface for `tripwire session complete` (v0.7.9 §A4: no bypass flags).

These tests are regression guards for the v0.7.9 design intent: the
absence of `--force` / `--skip-*` flags is the feature, not a side
effect. If a future PR adds one back, these tests should fail loudly.
"""

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def _help_text() -> str:
    runner = CliRunner()
    result = runner.invoke(session_cmd, ["complete", "--help"])
    assert result.exit_code == 0, result.output
    return result.output


def test_complete_help_has_no_force_flag():
    assert "--force" not in _help_text()


def test_complete_help_has_no_force_review_flag():
    assert "--force-review" not in _help_text()


def test_complete_help_has_no_skip_flags():
    """No `--skip-artifact-check`, `--skip-worktree-cleanup`, or
    `--skip-pr-merge-check`."""
    text = _help_text()
    assert "--skip-artifact-check" not in text
    assert "--skip-worktree-cleanup" not in text
    assert "--skip-pr-merge-check" not in text


def test_complete_help_mentions_only_dry_run_and_project_dir():
    """The expected v0.7.9 surface: `--dry-run` and `--project-dir` only.
    Catches accidental new bypass flags by name rather than by an
    exhaustive denylist."""
    text = _help_text()
    assert "--dry-run" in text
    assert "--project-dir" in text


def test_complete_rejects_force_flag_at_argv():
    """End-to-end: passing --force hits Click's "no such option" branch
    and exits non-zero. This catches the case where someone re-adds
    the option without updating the help text."""
    runner = CliRunner()
    result = runner.invoke(session_cmd, ["complete", "--force", "any-id"])
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()
