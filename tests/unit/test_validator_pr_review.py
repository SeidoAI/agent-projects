"""v0.12 — pr_review validator rules.

Four rules that gate the substance of `sessions/<sid>/pr-review.yaml`:

- ``pr_review/missing_evidence`` — empty `verified_by` arrays or
  placeholder evidence.
- ``pr_review/threshold_findings_unaddressed`` — non-empty
  `threshold_findings.unaddressed`.
- ``pr_review/external_reviewer_missing`` — config requires it but
  `external_reviews.codex.comment_url` is missing.
- ``pr_review/code_review_skill_missing`` — config requires it but
  `external_reviews.code_review_skill.invoked_at` is missing.

All four are gated on the manifest entry's `produced_at: in_review` —
they only fire on sessions at-or-past in_review (so executing-state
agents never see them, closing the kb-pivot trap shape from v0.11.1).

Missing-file enforcement is handled by `check_artifact_presence` via
the manifest entry, NOT by these rules — see `test_validator_pr_review_*`
that exercises the artifact/missing case once the manifest is wired up.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tripwire.core.validator import load_context
from tripwire.core.validator.checks.pr_review import (
    check_pr_review_code_review_skill,
    check_pr_review_evidence,
    check_pr_review_external_reviewer,
    check_pr_review_threshold_findings,
)


def _augment_manifest_with_pr_review(project_dir: Path) -> None:
    """Append pr-review manifest entry to the bare tmp_path_project.

    The bare fixture ships only `plan` in its manifest. The pr_review
    rules consult the manifest for the produced_at gate; without an
    entry, every check returns []. This helper writes the canonical
    shipping shape so tests can exercise the gate.
    """
    manifest_path = project_dir / "templates" / "artifacts" / "manifest.yaml"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["artifacts"].append(
        {
            "name": "pr-review",
            "file": "pr-review.yaml",
            "template": "pr-review.yaml.j2",
            "produced_at": "in_review",
            "produced_by": "pm",
            "owned_by": "pm",
            "required": True,
            "approval_gate": False,
        }
    )
    manifest_path.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture(autouse=True)
def _ensure_pr_review_manifest_entry(tmp_path_project: Path) -> None:
    _augment_manifest_with_pr_review(tmp_path_project)


def _seed_pr_review(project_dir: Path, sid: str, content: str) -> None:
    sdir = project_dir / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "pr-review.yaml").write_text(content, encoding="utf-8")


def _set_review_config(
    project_dir: Path,
    *,
    external_reviewer_mention: str | None = None,
    code_review_skill: str | None = None,
    severity_threshold: int = 65,
) -> None:
    project_yaml = project_dir / "project.yaml"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    data["review"] = {}
    if external_reviewer_mention is not None:
        data["review"]["external_reviewer_mention"] = external_reviewer_mention
    if code_review_skill is not None:
        data["review"]["code_review_skill"] = code_review_skill
    data["review"]["severity_threshold"] = severity_threshold
    project_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# pr_review/missing_evidence
# ---------------------------------------------------------------------------


class TestPrReviewEvidence:
    def test_empty_verified_by_fires(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump(
                {
                    "read_at": "2026-05-07T00:00:00Z",
                    "issues": [
                        {
                            "key": "TMP-1",
                            "acs": [
                                {
                                    "text": "thing happens",
                                    "verified_by": [],
                                    "decision": "verified",
                                }
                            ],
                        }
                    ],
                    "verdict": "approved",
                }
            ),
        )
        ctx = load_context(tmp_path_project)
        results = check_pr_review_evidence(ctx)
        codes = {r.code for r in results}
        assert "pr_review/missing_evidence" in codes

    def test_placeholder_text_fires(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="in_review")
        for placeholder in ("manual verification needed", "TBD", "<file:line>", "—"):
            _seed_pr_review(
                tmp_path_project,
                "s1",
                yaml.safe_dump(
                    {
                        "read_at": "2026-05-07T00:00:00Z",
                        "issues": [
                            {
                                "key": "TMP-1",
                                "acs": [
                                    {
                                        "text": "thing",
                                        "verified_by": [placeholder],
                                        "decision": "verified",
                                    }
                                ],
                            }
                        ],
                        "verdict": "approved",
                    }
                ),
            )
            ctx = load_context(tmp_path_project)
            results = check_pr_review_evidence(ctx)
            assert any(r.code == "pr_review/missing_evidence" for r in results), (
                f"placeholder {placeholder!r} should fire missing_evidence"
            )

    def test_real_evidence_passes(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump(
                {
                    "read_at": "2026-05-07T00:00:00Z",
                    "issues": [
                        {
                            "key": "TMP-1",
                            "acs": [
                                {
                                    "text": "module exists with all resources",
                                    "verified_by": [
                                        "modules/x/main.tf:1-58",
                                        "modules/x/variables.tf:1-32",
                                    ],
                                    "decision": "verified",
                                }
                            ],
                        }
                    ],
                    "verdict": "approved",
                }
            ),
        )
        ctx = load_context(tmp_path_project)
        assert check_pr_review_evidence(ctx) == []

    def test_pre_in_review_skips(self, tmp_path_project, save_test_session):
        """Sessions before in_review don't fire — produced_at gate."""
        save_test_session(tmp_path_project, "s1", status="executing")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump(
                {
                    "read_at": "2026-05-07T00:00:00Z",
                    "issues": [
                        {"key": "TMP-1", "acs": [{"text": "x", "verified_by": []}]}
                    ],
                    "verdict": "approved",
                }
            ),
        )
        ctx = load_context(tmp_path_project)
        assert check_pr_review_evidence(ctx) == []


# ---------------------------------------------------------------------------
# pr_review/threshold_findings_unaddressed
# ---------------------------------------------------------------------------


class TestPrReviewThresholdFindings:
    def test_unaddressed_fires(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump(
                {
                    "read_at": "2026-05-07T00:00:00Z",
                    "threshold_findings": {
                        "threshold": 65,
                        "count_above": 1,
                        "count_addressed": 0,
                        "unaddressed": [
                            {
                                "severity": 80,
                                "category": "security",
                                "location": "modules/x/main.tf:45",
                                "reason": "missing IAM policy condition",
                            }
                        ],
                    },
                    "verdict": "approved",
                }
            ),
        )
        ctx = load_context(tmp_path_project)
        results = check_pr_review_threshold_findings(ctx)
        codes = {r.code for r in results}
        assert "pr_review/threshold_findings_unaddressed" in codes
        # Hint should self-identify as PM action.
        hints = " ".join((r.fix_hint or "") for r in results)
        assert "PM action" in hints

    def test_empty_unaddressed_passes(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump(
                {
                    "read_at": "2026-05-07T00:00:00Z",
                    "threshold_findings": {
                        "threshold": 65,
                        "count_above": 1,
                        "count_addressed": 1,
                        "unaddressed": [],
                    },
                    "verdict": "approved",
                }
            ),
        )
        ctx = load_context(tmp_path_project)
        assert check_pr_review_threshold_findings(ctx) == []


# ---------------------------------------------------------------------------
# pr_review/external_reviewer_missing
# ---------------------------------------------------------------------------


class TestPrReviewExternalReviewer:
    def test_no_config_no_finding(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump({"read_at": "2026-05-07T00:00:00Z", "verdict": "approved"}),
        )
        ctx = load_context(tmp_path_project)
        # Default project config has no review block → rule skips silently.
        assert check_pr_review_external_reviewer(ctx) == []

    def test_configured_but_url_missing_fires(
        self, tmp_path_project, save_test_session
    ):
        _set_review_config(tmp_path_project, external_reviewer_mention="@codex")
        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump({"read_at": "2026-05-07T00:00:00Z", "verdict": "approved"}),
        )
        ctx = load_context(tmp_path_project)
        results = check_pr_review_external_reviewer(ctx)
        codes = {r.code for r in results}
        assert "pr_review/external_reviewer_missing" in codes
        # Mention name appears in the hint so the PM knows what to post.
        hints = " ".join((r.fix_hint or "") for r in results)
        assert "@codex" in hints

    def test_url_recorded_passes(self, tmp_path_project, save_test_session):
        _set_review_config(tmp_path_project, external_reviewer_mention="@codex")
        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump(
                {
                    "read_at": "2026-05-07T00:00:00Z",
                    "external_reviews": {
                        "codex": {
                            "posted_at": "2026-05-07T15:45:00Z",
                            "comment_url": "https://github.com/x/y/pull/1#issuecomment-1",
                        }
                    },
                    "verdict": "approved",
                }
            ),
        )
        ctx = load_context(tmp_path_project)
        assert check_pr_review_external_reviewer(ctx) == []


# ---------------------------------------------------------------------------
# pr_review/code_review_skill_missing
# ---------------------------------------------------------------------------


class TestPrReviewCodeReviewSkill:
    def test_no_config_no_finding(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump({"read_at": "2026-05-07T00:00:00Z", "verdict": "approved"}),
        )
        ctx = load_context(tmp_path_project)
        assert check_pr_review_code_review_skill(ctx) == []

    def test_configured_but_invoked_at_missing_fires(
        self, tmp_path_project, save_test_session
    ):
        _set_review_config(
            tmp_path_project,
            code_review_skill="superpowers:code-review:code-review",
        )
        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump({"read_at": "2026-05-07T00:00:00Z", "verdict": "approved"}),
        )
        ctx = load_context(tmp_path_project)
        results = check_pr_review_code_review_skill(ctx)
        codes = {r.code for r in results}
        assert "pr_review/code_review_skill_missing" in codes

    def test_invocation_recorded_passes(self, tmp_path_project, save_test_session):
        _set_review_config(
            tmp_path_project,
            code_review_skill="superpowers:code-review:code-review",
        )
        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump(
                {
                    "read_at": "2026-05-07T00:00:00Z",
                    "external_reviews": {
                        "code_review_skill": {
                            "skill": "superpowers:code-review:code-review",
                            "invoked_at": "2026-05-07T15:46:00Z",
                            "findings": [],
                        }
                    },
                    "verdict": "approved",
                }
            ),
        )
        ctx = load_context(tmp_path_project)
        assert check_pr_review_code_review_skill(ctx) == []


# ---------------------------------------------------------------------------
# Integration — atomic transition + pr_review gates
# ---------------------------------------------------------------------------


class TestPrReviewTransitionGate:
    """v0.12: transition→verified now runs validate atomically and rolls
    back if any pr_review/* fires. This is the user-visible behaviour
    that closes handoff #3."""

    def test_transition_to_verified_blocked_by_missing_evidence(
        self, tmp_path_project, save_test_session
    ):
        from click.testing import CliRunner

        from tripwire.cli.session import session_cmd
        from tripwire.core.session_store import load_session

        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            yaml.safe_dump(
                {
                    "read_at": "2026-05-07T00:00:00Z",
                    "issues": [
                        {
                            "key": "TMP-1",
                            "acs": [
                                {
                                    "text": "thing",
                                    "verified_by": ["manual verification needed"],
                                    "decision": "verified",
                                }
                            ],
                        }
                    ],
                    "verdict": "approved",
                }
            ),
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "transition",
                "s1",
                "verified",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        assert "pr_review/missing_evidence" in result.output
        # Status was rolled back.
        assert load_session(tmp_path_project, "s1").status == "in_review"


class TestPrepareReviewCmd:
    """v0.12: `tripwire session prepare-review <sid>` scaffolds
    pr-review.yaml from the session's member-issue ACs."""

    def test_scaffolds_skeleton_from_member_issues(
        self, tmp_path_project, save_test_session, save_test_issue
    ):
        from click.testing import CliRunner

        from tripwire.cli.session import session_cmd

        # Issue with three explicit ACs.
        ac_body = (
            "## Context\nx\n\n"
            "## Acceptance criteria\n"
            "- [ ] alpha thing implemented\n"
            "- [ ] beta thing tested\n"
            "- [ ] gamma thing documented\n\n"
            "## Test plan\n```\nuv run pytest\n```\n"
        )
        save_test_issue(tmp_path_project, "TMP-1", body=ac_body)
        save_test_session(tmp_path_project, "s1", status="in_review", issues=["TMP-1"])

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "prepare-review",
                "s1",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code == 0, result.output

        target = tmp_path_project / "sessions" / "s1" / "pr-review.yaml"
        assert target.is_file()
        scaffold = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert scaffold["verdict"] == "approved"
        assert len(scaffold["issues"]) == 1
        issue_block = scaffold["issues"][0]
        assert issue_block["key"] == "TMP-1"
        # Three ACs scaffolded with empty evidence (so the validator's
        # missing_evidence rule fires until the PM fills them in).
        assert len(issue_block["acs"]) == 3
        assert all(ac["verified_by"] == [] for ac in issue_block["acs"])
        ac_texts = [ac["text"] for ac in issue_block["acs"]]
        assert any("alpha" in t for t in ac_texts)

    def test_refuses_overwrite_without_force(self, tmp_path_project, save_test_session):
        from click.testing import CliRunner

        from tripwire.cli.session import session_cmd

        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            "# existing content\nverdict: approved\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "prepare-review",
                "s1",
                "--project-dir",
                str(tmp_path_project),
            ],
        )
        assert result.exit_code != 0
        assert "already exists" in result.output
        # Original content preserved.
        target = tmp_path_project / "sessions" / "s1" / "pr-review.yaml"
        assert "existing content" in target.read_text(encoding="utf-8")

    def test_force_overwrites(self, tmp_path_project, save_test_session):
        from click.testing import CliRunner

        from tripwire.cli.session import session_cmd

        save_test_session(tmp_path_project, "s1", status="in_review")
        _seed_pr_review(
            tmp_path_project,
            "s1",
            "# existing content\nverdict: approved\n",
        )

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            [
                "prepare-review",
                "s1",
                "--project-dir",
                str(tmp_path_project),
                "--force",
            ],
        )
        assert result.exit_code == 0, result.output
        target = tmp_path_project / "sessions" / "s1" / "pr-review.yaml"
        assert "existing content" not in target.read_text(encoding="utf-8")
        # Newly scaffolded structure is parseable YAML with verdict.
        scaffold = yaml.safe_load(target.read_text(encoding="utf-8"))
        assert "verdict" in scaffold
