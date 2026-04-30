"""Write artifacts produced by ``tripwire session review``.

The CLI command at ``cli/session.py:session_review_cmd`` orchestrates
review-output side-effects: gather PR number + files via gh, render
each issue's ``verified.md``, and persist ``sessions/<sid>/review.json``
for the complete-time gate. The pure side-effect helpers live here so
they're independently importable + testable.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

import tripwire
from tripwire.core import paths
from tripwire.core.store import load_issue


def gather_pr_number(session) -> int | None:
    """Look up the merged PR number for *session* via ``gh pr list``.

    Walks each recorded worktree and returns the first PR found. Returns
    ``None`` on transport errors / no PR.
    """
    for wt in session.runtime_state.worktrees:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--head",
                    wt.branch,
                    "--json",
                    "number",
                    "--limit",
                    "1",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                prs = json.loads(result.stdout)
                if prs:
                    return int(prs[0]["number"])
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
            continue
    return None


def gather_pr_files(pr_number: int) -> list[str]:
    """Return the list of file paths in *pr_number* via ``gh pr view``.

    Returns an empty list on any transport error.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "files"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return [f["path"] for f in data.get("files", [])]
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        pass
    return []


def render_verified_md(
    *, issue, criteria: list[str], verdict: str, stamp: str, deviations: list[str]
) -> str:
    """Render the shipped ``verified.md.j2`` template with review context."""
    template_root = Path(tripwire.__file__).parent / "templates" / "issue_artifacts"
    env = Environment(
        loader=FileSystemLoader(str(template_root)),
        keep_trailing_newline=True,
    )
    template = env.get_template("verified.md.j2")
    return template.render(
        issue=issue,
        criteria=criteria,
        verdict=verdict,
        verified_by="pm-agent",
        verified_at=stamp,
        deviations=deviations,
    )


def write_verified_for_session(project_dir: Path, session, report) -> None:
    """For each issue in the session, write or append ``issues/<key>/verified.md``.

    New file: rendered via ``templates/issue_artifacts/verified.md.j2``.
    Existing file: append a ``## Re-review <date>`` section preserving history.
    """
    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    for ir in report.issue_reviews:
        verified_path = paths.issue_dir(project_dir, ir.key) / "verified.md"
        if verified_path.is_file():
            existing = verified_path.read_text(encoding="utf-8")
            addition = (
                f"\n\n## Re-review {stamp} (session {session.id})\n"
                f"Verdict: {report.verdict}\n"
            )
            verified_path.write_text(existing + addition, encoding="utf-8")
            continue

        try:
            issue = load_issue(project_dir, ir.key)
        except FileNotFoundError:
            continue
        rendered = render_verified_md(
            issue=issue,
            criteria=ir.criteria,
            verdict=report.verdict,
            stamp=stamp,
            deviations=report.deviations.unspec_files,
        )
        verified_path.parent.mkdir(parents=True, exist_ok=True)
        verified_path.write_text(rendered, encoding="utf-8")


def write_review_json(project_dir: Path, session, report) -> None:
    """Persist ``sessions/<id>/review.json`` for the complete-time gate."""
    review_path = project_dir / "sessions" / session.id / "review.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)

    head_sha = None
    if session.runtime_state.worktrees:
        wt_path = Path(session.runtime_state.worktrees[0].worktree_path)
        if wt_path.is_dir():
            try:
                result = subprocess.run(
                    ["git", "-C", str(wt_path), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    head_sha = result.stdout.strip() or None
            except (subprocess.SubprocessError, OSError):
                pass

    payload = {
        "session_id": session.id,
        "verdict": report.verdict,
        "exit_code": report.exit_code,
        "pr_number": report.pr_number,
        "head_sha": head_sha,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    review_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
