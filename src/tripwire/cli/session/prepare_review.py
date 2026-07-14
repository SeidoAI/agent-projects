"""``tripwire session prepare-review`` — scaffold pr-review.yaml from issue ACs."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


@session_cmd.command("prepare-review")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite an existing pr-review.yaml.",
)
def session_prepare_review_cmd(
    session_id: str,
    project_dir: Path,
    force: bool,
) -> None:
    """Scaffold `sessions/<sid>/pr-review.yaml` from the session's
    member-issue ACs.

    PM-review enforcement: the PM runs this as the first step of
    `/pm-session-review`, then fills in `verified_by` evidence,
    four-lens findings, external-reviewer signals, and threshold-finding
    decisions before transitioning the session to `verified`. The
    validator's `pr_review/*` rules gate that transition on the file's
    substance.

    Refuses to overwrite an existing pr-review.yaml unless `--force` is
    set, so a partially-filled review isn't blown away.
    """
    import re as _re
    from datetime import datetime, timezone

    from tripwire.core.store import load_issue

    def parse_acceptance_criteria_from_body(body: str | None) -> list[str]:
        """Pull the `## Acceptance criteria` checklist out of an issue
        body. Returns the raw bullet text minus the `[ ]` / `[x]` prefix.

        Tolerant: matches `## Acceptance criteria` (case-insensitive) and
        accepts any subsequent indentation level for bullets. Stops at the
        next `##` heading.
        """
        if not body:
            return []
        lines = body.splitlines()
        in_section = False
        items: list[str] = []
        for line in lines:
            stripped = line.strip()
            if _re.match(r"^##\s+acceptance criteria\b", stripped, _re.IGNORECASE):
                in_section = True
                continue
            if in_section and stripped.startswith("##"):
                break
            if not in_section:
                continue
            m = _re.match(r"^[-*]\s*(?:\[[ xX]\]\s*)?(.+)$", stripped)
            if m:
                items.append(m.group(1).strip())
        return items

    from tripwire.core import paths as _paths

    resolved, session = _resolve_and_load_session(project_dir, session_id)

    sdir = _paths.session_dir(resolved, session_id)
    sdir.mkdir(parents=True, exist_ok=True)
    target = sdir / "pr-review.yaml"
    if target.exists() and not force:
        raise click.ClickException(
            f"{target.relative_to(resolved)} already exists; pass --force to overwrite."
        )

    issues_block: list[dict] = []
    for issue_key in session.issues:
        try:
            issue = load_issue(resolved, issue_key)
        except FileNotFoundError:
            continue
        acs = parse_acceptance_criteria_from_body(issue.body)
        issues_block.append(
            {
                "key": issue_key,
                "acs": [
                    {
                        "text": ac,
                        "verified_by": [],
                        "decision": "verified",
                    }
                    for ac in (acs or ["<no acceptance criteria found in issue body>"])
                ],
            }
        )

    skeleton = {
        "read_at": datetime.now(tz=timezone.utc).isoformat(),
        "read_by": "pm",
        "pr": {"code": None, "pt": None},
        "issues": issues_block,
        "four_lens": {
            "ac_met_but_not_really": {"findings": []},
            "unilateral_decisions": {"findings": []},
            "skipped_workflow": {"findings": []},
            "quality_degradation": {"findings": []},
        },
        "external_reviews": {},
        "threshold_findings": {
            "threshold": 65,
            "count_above": 0,
            "count_addressed": 0,
            "unaddressed": [],
        },
        "verdict": "approved",
    }

    import yaml as _yaml

    target.write_text(
        "# PM-review record. Fill `verified_by` arrays with concrete\n"
        "# file:line citations or short evidence strings before transitioning\n"
        "# the session to `verified`. The validator's pr_review/* rules\n"
        "# block transition on placeholders or missing evidence.\n\n"
        + _yaml.safe_dump(skeleton, sort_keys=False),
        encoding="utf-8",
    )
    click.echo(f"Scaffolded {target.relative_to(resolved)}")
    click.echo(
        f"  {len(issues_block)} issue(s), "
        f"{sum(len(i['acs']) for i in issues_block)} AC(s)"
    )
    click.echo("Next: fill `verified_by` arrays + four_lens findings, then run")
    click.echo(f"  tripwire session transition {session_id} verified")
