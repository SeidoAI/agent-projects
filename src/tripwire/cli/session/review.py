"""``tripwire session review`` — PR diff vs. issue specs."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.core.session_review_writer import (
    gather_pr_files as _gather_pr_files,
)
from tripwire.core.session_review_writer import (
    gather_pr_number as _gather_pr_number,
)
from tripwire.core.session_review_writer import (
    render_verified_md as _render_verified_md,  # noqa: F401  — re-exported for tests
)
from tripwire.core.session_review_writer import (
    write_review_json as _write_review_json,
)
from tripwire.core.session_review_writer import (
    write_verified_for_session as _write_verified_for_session,
)
from tripwire.core.session_store import load_session


@session_cmd.command("review")
@click.argument("session_id")
@click.option(
    "--pr",
    "pr_number",
    type=int,
    default=None,
    help="PR number (auto-detected from worktree branch if omitted).",
)
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.option(
    "--post-pr-comments/--no-post-pr-comments",
    default=False,
    help="Post review findings as a PR comment via `gh`.",
)
@click.option(
    "--write-verified/--no-write-verified",
    default=True,
    help="Write/update issues/<key>/verified.md for each issue in the session.",
)
def session_review_cmd(
    session_id: str,
    pr_number: int | None,
    project_dir: Path,
    output_format: str,
    post_pr_comments: bool,
    write_verified: bool,
) -> None:
    """Review a session's PR against the session's issue specs."""
    import json as _json
    from dataclasses import asdict

    from tripwire.core import paths as _paths
    from tripwire.core.session_review import (
        IssueReview,
        ReviewReport,
        check_plan_adherence,
        detect_deviations,
        parse_acceptance_criteria,
        parse_repo_scope,
    )
    from tripwire.core.store import load_issue

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    session = load_session(resolved, session_id)

    if pr_number is None:
        pr_number = _gather_pr_number(session)

    pr_files = _gather_pr_files(pr_number) if pr_number is not None else []

    report = ReviewReport(session_id=session_id, pr_number=pr_number)

    scope_paths: list[str] = []
    for issue_key in session.issues:
        try:
            issue = load_issue(resolved, issue_key)
        except FileNotFoundError:
            continue
        criteria = parse_acceptance_criteria(issue.body)
        report.issue_reviews.append(
            IssueReview(
                key=issue_key,
                criteria=criteria,
                criteria_met=[False] * len(criteria),
                criteria_evidence=[None] * len(criteria),
            )
        )
        scope_paths.extend(parse_repo_scope(issue.body))

    devs = detect_deviations(pr_files, scope_paths)
    report.deviations.unspec_files = devs["unspec_files"]

    plan_path = _paths.session_plan_path(resolved, session_id)
    if plan_path.is_file():
        ok, unmatched = check_plan_adherence(
            plan_path.read_text(encoding="utf-8"), pr_files
        )
        report.plan_adherence_ok = ok
        report.plan_unmatched_steps = unmatched

    if report.deviations.unspec_files or not report.plan_adherence_ok:
        report.verdict = "approved_with_notes"

    if output_format == "json":
        click.echo(_json.dumps(asdict(report), indent=2, default=str))
    else:
        click.echo(
            f"Session Review: {session_id} (PR "
            f"{f'#{pr_number}' if pr_number else 'not found'})\n"
        )
        click.echo(f"Verdict: {report.verdict}")
        click.echo("\nIssues:")
        for ir in report.issue_reviews:
            click.echo(
                f"  {ir.key}: {len(ir.criteria)} criteria (manual verification needed)"
            )
        if report.deviations.unspec_files:
            click.echo("\nDeviations (unspec'd files):")
            for f in report.deviations.unspec_files:
                click.echo(f"  - {f}")
        if report.plan_unmatched_steps:
            click.echo("\nPlan adherence issues:")
            for s in report.plan_unmatched_steps:
                click.echo(f"  - {s} (named in plan, absent from PR)")

    if post_pr_comments and pr_number:
        comment_lines = [
            "## Tripwire session review",
            "",
            f"Verdict: `{report.verdict}`",
        ]
        if report.deviations.unspec_files:
            comment_lines.append("")
            comment_lines.append("**Files outside issue scope:**")
            for f in report.deviations.unspec_files:
                comment_lines.append(f"- `{f}`")
        try:
            subprocess.run(
                [
                    "gh",
                    "pr",
                    "comment",
                    str(pr_number),
                    "--body",
                    "\n".join(comment_lines),
                ],
                check=True,
                capture_output=True,
            )
            if output_format == "text":
                click.echo(f"\n(posted to PR #{pr_number})")
        except (subprocess.SubprocessError, OSError):
            if output_format == "text":
                click.echo(f"\n(failed to post to PR #{pr_number})")

    if write_verified:
        _write_verified_for_session(resolved, session, report)

    # Write review.json artifact for session_complete's review-exit-code gate
    # (spec §11.2 step 4). Always — regardless of output_format or other flags —
    # so that subsequent `session complete` can consult a deterministic record.
    _write_review_json(resolved, session, report)

    raise click.exceptions.Exit(report.exit_code)
