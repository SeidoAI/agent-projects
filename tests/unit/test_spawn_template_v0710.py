"""v0.7.10 §3.B1 + §3.B3 — spawn template additions for CI-aware exit.

The v0.7.9 batch already added `gh pr checks --watch` and the
3-attempt cap (see `test_spawn_template_v079.py::TestCIAwareExit`).
The v0.7.10 batch tightens the loop:

  - B1: when a CI check fails, the agent must read the failure output
    via ``gh run view ID --log-failed`` before pushing a fix. Without
    this step, agents push speculative fixes against noise.
  - B3: when fixing a CI test failure, the agent must identify the
    *pattern* of the failure (missing flag, broken precondition) and
    grep the test suite for sibling occurrences. Patch them all in
    one commit. The 2026-04-25 batch had two PRs (#33, #35) where the
    agent fixed only the test mentioned in the CI log and triggered
    a second red-CI cycle on the next sibling.

These properties are asserted as substring invariants on the rendered
prompt template (and `system_prompt_append` for B3) — kept loose
enough to survive copy edits, strict enough to catch a regression
that drops the language entirely.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tripwire


def _load_defaults() -> dict:
    path = Path(tripwire.__file__).parent / "templates" / "spawn" / "defaults.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class TestB1FailureOutputInvestigation:
    """B1 — agent reads CI failure output before pushing a fix."""

    def test_gh_run_view_log_failed_referenced(self):
        tpl = _load_defaults()["prompt_template"]
        # The spec specifically calls out `gh run view <id> --log-failed`
        # so the agent reads the failing job's log rather than guessing
        # from the rollup summary.
        assert "gh run view" in tpl
        assert "--log-failed" in tpl

    def test_failure_investigation_precedes_fix(self):
        """Read the failure, then push the fix. The opposite ordering
        means the agent fires a guess-fix and waits for the next
        red-CI cycle to see what actually broke."""
        tpl = _load_defaults()["prompt_template"]
        run_view_idx = tpl.find("gh run view")
        # `push a fix` / `fix commit` — accept either phrasing as long
        # as it appears AFTER the failure-read step.
        fix_idx = tpl.find("fix commit")
        if fix_idx < 0:
            fix_idx = tpl.find("push a fix")
        assert run_view_idx >= 0 and fix_idx >= 0
        assert run_view_idx < fix_idx, (
            "gh run view --log-failed must appear BEFORE the fix-push step"
        )


class TestB3GrepThePattern:
    """B3 — fix the pattern, not the symptom."""

    def test_grep_pattern_in_prompt_template(self):
        tpl = _load_defaults()["prompt_template"]
        # Loose match — accept "grep the test suite" or
        # "grep the entire test suite" or similar.
        normalized = tpl.lower()
        assert "grep" in normalized
        assert "pattern" in normalized
        # And the "fix every occurrence in one commit" cue so the
        # agent doesn't split fixes across three commits.
        assert (
            "every occurrence" in normalized
            or "all occurrences" in normalized
            or "patch them all" in normalized
            or "in one commit" in normalized
        )

    def test_grep_pattern_in_system_prompt_append(self):
        """B3 must appear in both slots: the kickoff prompt is read once
        at spawn, but `system_prompt_append` is injected on every turn
        — so a CI failure 50 turns into the session still gets the
        guidance."""
        sys_append = _load_defaults()["system_prompt_append"]
        normalized = sys_append.lower()
        assert "grep" in normalized
        assert "pattern" in normalized
