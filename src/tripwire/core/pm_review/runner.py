"""``run_pm_review`` — the pm-review station's runner.

The runner:

1. Confirms the session exists.
2. Calls :func:`tripwire.core.validator.validate_project` (strict).
3. Partitions the report by named pm-review check.
4. Synthesises a verdict — ``auto-merge`` when every named check
   passes, ``request_changes`` otherwise.
5. Writes ``sessions/<sid>/artifacts/pm-review.md``.
6. Emits ``pm_review.completed`` to the events log under workflow
   ``pm-review`` so the events viewer + drift detector pick it up.

``re-engage`` is a verdict the runner exposes in the type but does not
auto-derive — it's a PM judgment call ("this session diverged so badly
it needs respawning"). Callers can construct a re-engage verdict
externally; the runner's auto-derivation never picks it.

The runner deliberately does not use ``@registers_at("pm-review",
"review")`` to cross-register the validator functions. The decorator
overwrites ``__tripwire_workflow_station__`` on the function (it tracks
only one pair for event-emission), so a second decoration would
reroute the events emitted during a coding-session ``validate_project``
run from ``coding-session`` → ``pm-review`` and break the existing
events log shape. Instead we run validators normally and partition
their results here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from tripwire.core.events.log import emit_event
from tripwire.core.pm_review.checks import PM_REVIEW_CHECKS, name_for_finding_code
from tripwire.core.validator import validate_project
from tripwire.core.validator._types import CheckResult, ValidationReport

PM_REVIEW_WORKFLOW = "pm-review"
PM_REVIEW_STATION = "review"
PM_REVIEW_ARTIFACT_FILENAME = "pm-review.md"


PMReviewOutcome = Literal["auto-merge", "request_changes", "re-engage"]


@dataclass(frozen=True)
class PMReviewCheck:
    """One named check's outcome."""

    name: str
    validator_id: str
    outcome: Literal["pass", "fail"]
    findings: list[CheckResult] = field(default_factory=list)


@dataclass(frozen=True)
class PMReviewVerdict:
    """The full verdict for one pm-review run."""

    session_id: str
    verdict: PMReviewOutcome
    checks: list[PMReviewCheck]
    artifact_path: Path
    started_at: str
    finished_at: str


def run_pm_review(
    project_dir: Path,
    *,
    session_id: str,
    now: datetime | None = None,
) -> PMReviewVerdict:
    """Execute the pm-review station for *session_id*.

    Raises :class:`FileNotFoundError` when the session directory is
    missing — the PM is reviewing a session that doesn't exist.
    """
    session_dir = project_dir / "sessions" / session_id
    if not session_dir.is_dir():
        raise FileNotFoundError(f"session {session_id!r} not found at {session_dir}")
    artifacts_dir = session_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    started = now or datetime.now(tz=timezone.utc)
    # Pass session_id through so the validator's per-check
    # `validator.run` workflow events log under `instance=<session>`
    # rather than the CLI sentinel (`_cli_validate`). Without this,
    # `/workflow-stats` by-instance counts skew and the Event Log
    # filter on the reviewed session misses the rerun rows.
    report = validate_project(project_dir, strict=True, session_id=session_id)
    finished = datetime.now(tz=timezone.utc)

    checks = _partition_findings(report)
    verdict = _verdict_from_checks(checks)

    artifact_path = artifacts_dir / PM_REVIEW_ARTIFACT_FILENAME
    artifact_path.write_text(
        _render_artifact(
            session_id=session_id,
            verdict=verdict,
            checks=checks,
            started=started,
            finished=finished,
        ),
        encoding="utf-8",
    )

    emit_event(
        project_dir,
        workflow=PM_REVIEW_WORKFLOW,
        instance=session_id,
        station=PM_REVIEW_STATION,
        event="pm_review.completed",
        details={
            "outcome": verdict,
            "failed_checks": [c.name for c in checks if c.outcome == "fail"],
            "passed_checks": [c.name for c in checks if c.outcome == "pass"],
        },
        now=finished,
    )

    return PMReviewVerdict(
        session_id=session_id,
        verdict=verdict,
        checks=checks,
        artifact_path=artifact_path,
        started_at=_iso_z(started),
        finished_at=_iso_z(finished),
    )


def _partition_findings(report: ValidationReport) -> list[PMReviewCheck]:
    """Bucket the report's findings into the 10 named pm-review checks.

    A finding routes to its named check via the ``code`` prefix (see
    :func:`tripwire.core.pm_review.checks.name_for_finding_code`).
    Unmapped prefixes route to a synthetic ``other`` bucket, which
    forces a ``request_changes`` verdict — better to surface the
    finding in a generic bucket than silently lose it.
    """
    by_name: dict[str, list[CheckResult]] = {n: [] for n, _ in PM_REVIEW_CHECKS}
    other: list[CheckResult] = []
    # `report.errors` already includes warnings under strict=True.
    for f in report.errors:
        name = name_for_finding_code(f.code)
        if name is None:
            other.append(f)
            continue
        by_name.setdefault(name, []).append(f)

    out: list[PMReviewCheck] = []
    for name, validator_id in PM_REVIEW_CHECKS:
        bucket = by_name.get(name, [])
        out.append(
            PMReviewCheck(
                name=name,
                validator_id=validator_id,
                outcome="fail" if bucket else "pass",
                findings=list(bucket),
            )
        )
    if other:
        out.append(
            PMReviewCheck(
                name="other",
                validator_id="",
                outcome="fail",
                findings=other,
            )
        )
    return out


def _verdict_from_checks(checks: list[PMReviewCheck]) -> PMReviewOutcome:
    """All-pass → ``auto-merge``; any fail → ``request_changes``.

    ``re-engage`` is never auto-derived (see module docstring).
    """
    return (
        "auto-merge" if all(c.outcome == "pass" for c in checks) else "request_changes"
    )


def _render_artifact(
    *,
    session_id: str,
    verdict: PMReviewOutcome,
    checks: list[PMReviewCheck],
    started: datetime,
    finished: datetime,
) -> str:
    """Render the ``pm-review.md`` artifact body."""
    lines: list[str] = [
        f"# pm-review — {session_id}",
        "",
        f"**Verdict:** `{verdict}`",
        f"**Started:** {_iso_z(started)}",
        f"**Finished:** {_iso_z(finished)}",
        "",
        "## Checks",
        "",
        "| # | Check | Outcome | Findings |",
        "|---|-------|---------|----------|",
    ]
    for i, check in enumerate(checks, start=1):
        marker = "✓" if check.outcome == "pass" else "✗"
        lines.append(
            f"| {i} | {check.name} | {marker} {check.outcome} | {len(check.findings)} |"
        )
    lines.append("")
    failing = [c for c in checks if c.outcome == "fail"]
    if failing:
        lines.append("## Findings")
        lines.append("")
        for check in failing:
            lines.append(f"### {check.name}")
            lines.append("")
            for f in check.findings:
                file_part = f" — `{f.file}`" if f.file else ""
                lines.append(f"- `{f.code}`{file_part}: {f.message}")
            lines.append("")
    return "\n".join(lines)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "PM_REVIEW_ARTIFACT_FILENAME",
    "PM_REVIEW_STATION",
    "PM_REVIEW_WORKFLOW",
    "PMReviewCheck",
    "PMReviewOutcome",
    "PMReviewVerdict",
    "run_pm_review",
]
