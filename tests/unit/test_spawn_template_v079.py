"""v0.7.9 §A5 — spawn template rewrite (defaults.yaml prompt_template).

Three requirements per spec:

1. Exit protocol is unconditional. NO "if there are two PRs..."
   conditional language. Both code PR AND PT PR MUST exist.

2. Self-review.md is an explicit pre-PT-PR step. Agent writes
   ``sessions/<sid>/self-review.md`` from the four-lens template before
   pushing the PT PR. PR comment is generated FROM the file.

3. CI-aware exit: agent polls ``gh pr checks <num> --watch`` after
   PR opens. After 3 failed-fix attempts, plain-text stop for PM.

These properties are asserted as invariants on the rendered prompt
template — substring searches kept loose enough to survive minor
copy edits but strict enough to catch a regression that drops the
mandatory language entirely.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tripwire


def _load_default_template() -> str:
    path = (
        Path(tripwire.__file__).parent / "templates" / "spawn" / "defaults.yaml"
    )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["prompt_template"]


class TestUnconditionalExitProtocol:
    """A5.1 — exit protocol must not be conditional on PR count."""

    def test_no_conditional_two_prs_phrase(self):
        tpl = _load_default_template()
        # The pre-v0.7.9 wording was:
        #   "If there are two PRs (code + project-tracking), cross-link them"
        # That permissive reading is the reason 3-of-6 agents on
        # 2026-04-25 opened only the code PR. v0.7.9 ditches it.
        assert "If there are two PRs" not in tpl
        assert "if there are two PRs" not in tpl

    def test_both_prs_must_exist(self):
        tpl = _load_default_template()
        # The new mandatory language: both PRs MUST exist. Loose match
        # so we tolerate "Both code PR AND PT PR" / "both PRs"
        # phrasing variations.
        normalized = tpl.lower()
        assert "must exist" in normalized
        assert "both" in normalized and "pr" in normalized

    def test_artifact_violation_language_present(self):
        tpl = _load_default_template()
        assert "protocol violation" in tpl.lower()


class TestSelfReviewExplicit:
    """A5.2 — self-review.md is a required commit before PT PR."""

    def test_self_review_md_path_referenced(self):
        tpl = _load_default_template()
        assert "self-review.md" in tpl

    def test_four_lens_template_referenced(self):
        tpl = _load_default_template()
        # Either the j2 template path or the four-lens phrase must
        # appear so the agent knows where to look.
        assert (
            "self-review.md.j2" in tpl
            or "four-lens" in tpl.lower()
            or "four lens" in tpl.lower()
        )

    def test_committed_before_pt_pr(self):
        tpl = _load_default_template()
        # Loose match on the temporal ordering: self-review must be
        # committed (not just authored as a PR comment).
        normalized = tpl.lower()
        assert (
            "commit" in normalized and "self-review" in normalized
        )


class TestCIAwareExit:
    """A5.3 — agent polls CI checks after PR opens, capped at 3 attempts."""

    def test_gh_pr_checks_watch_referenced(self):
        tpl = _load_default_template()
        assert "gh pr checks" in tpl

    def test_three_attempt_cap_present(self):
        tpl = _load_default_template()
        # Either "3 attempts" / "three attempts" / "3 fail" — match
        # the digit form (the spec uses it).
        normalized = tpl.lower()
        assert "3 " in normalized
        # And cap-relevant phrasing.
        assert "attempt" in normalized or "fix" in normalized

    def test_plain_text_stop_for_pm_after_cap(self):
        tpl = _load_default_template()
        normalized = tpl.lower()
        assert "plain text" in normalized or "plain-text" in normalized
        assert "pm" in normalized


class TestTemplateStillRenders:
    """Smoke: the rewritten template must still interpolate with the
    keys ``render_prompt`` passes — agent / session_id / session_name /
    branch_type / plan."""

    def test_renders_with_expected_keys(self):
        from tripwire.core.spawn_config import (
            load_resolved_spawn_config,
            render_prompt,
        )

        # Load defaults via the real resolver against a fresh tmp dir
        # so we don't depend on a project context.
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            resolved = load_resolved_spawn_config(Path(td), session=None)
            out = render_prompt(
                resolved,
                plan="<plan body>",
                agent="backend-coder",
                session_id="session-test",
                session_name="Test session",
                branch_type="feat",
            )
        assert "session-test" in out
        assert "<plan body>" in out
