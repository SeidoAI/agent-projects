"""`tripwire validate-plan <session-id>` — pre-spawn coherence gate.

Catches the failure mode the testing-backend trial surfaced: plan
written months ago, repo state has moved on, plan still says "create
file X" when X already exists. PM should run this before queueing a
session so the plan can be fixed in 30 seconds rather than the agent
discovering the divergence in 14 minutes of $4.74 reconnaissance.

v0.7.3 ships four checks:
- `plan/missing`            — plan.md doesn't exist
- `plan/unresolved_ref`     — [[id]] references a non-existent node
- `plan/create_target_exists` — heuristic: step says "create X" but X exists
- `plan/modify_target_missing` — heuristic: step says "modify X" but X is missing

The v0.8 spec
(`docs/specs/2026-04-24-v08-bidirectional-concept-graph.md` §7.2)
extends this with version-pin freshness checks. The v0.7.3 implementation
is designed for clean extension — same dataclass shape, additive fields.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import click

from tripwire.core.concept_context import extract_plan_concepts
from tripwire.core.paths import session_plan_path
from tripwire.core.session_store import load_session

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class PlanCheckResult:
    """One finding from `validate-plan`."""

    code: str
    severity: Severity
    message: str
    location: str | None = None  # e.g. "plan.md:14"


@dataclass
class PlanReport:
    """Aggregate result of all plan checks for a session."""

    session_id: str
    errors: list[PlanCheckResult] = field(default_factory=list)
    warnings: list[PlanCheckResult] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if self.errors:
            return 2
        if self.warnings:
            return 1
        return 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "session_id": self.session_id,
                "errors": [r.__dict__ for r in self.errors],
                "warnings": [r.__dict__ for r in self.warnings],
                "exit_code": self.exit_code,
            },
            indent=2,
        )


# Heuristic: a step heading + its body until the next step heading.
_STEP_HEADING = re.compile(r"^###\s+Step\b.*$", re.MULTILINE)
# Verbs that suggest "this step creates a new file".
_CREATE_VERBS = re.compile(r"\b(create|add|implement|new|scaffold)\b", re.IGNORECASE)
# Verbs that suggest "this step changes an existing file".
_MODIFY_VERBS = re.compile(
    r"\b(modify|update|change|refactor|edit|rewrite|extend)\b", re.IGNORECASE
)
# Backtick-quoted path that contains a "/" or ends with a known extension.
_BACKTICK_PATH = re.compile(r"`([^`\s]*[/.][^`\s]+)`")


def _split_into_steps(body: str) -> list[str]:
    """Split a plan into per-step sections by `### Step …` headings.

    Content before the first step heading is dropped (typically Context,
    Issues in scope, Repos — not actionable steps).
    """
    matches = list(_STEP_HEADING.finditer(body))
    if not matches:
        return []
    sections: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections.append(body[start:end])
    return sections


def _classify_step(step_text: str) -> Literal["create", "modify", "other"]:
    """Pick the verb class from the step's title line only.

    The title is where the verb signal is unambiguous. Step bodies
    contain boilerplate labels like `**Change:**` (the conventional
    description-of-work label, not an actual modify-verb) that produce
    false positives if scanned.
    """
    lines = step_text.splitlines()
    if not lines:
        return "other"
    title = lines[0]
    has_create = bool(_CREATE_VERBS.search(title))
    has_modify = bool(_MODIFY_VERBS.search(title))
    if has_create and not has_modify:
        return "create"
    if has_modify and not has_create:
        return "modify"
    # Both or neither → don't classify; skip heuristic for this step.
    return "other"


def _extract_paths(step_text: str) -> list[str]:
    """Extract candidate file paths from a step's `**Files:**` block.

    Looks for backtick-quoted tokens containing `/` or `.`. Filters out
    anything that's clearly a CLI command (starts with `tripwire`,
    `git`, `uv`, `gh`, `npm`, `cd`, etc.).
    """
    cli_prefixes = ("tripwire", "git", "uv", "gh", "npm", "cd", "claude", "tw ")
    paths: list[str] = []
    seen: set[str] = set()
    for m in _BACKTICK_PATH.finditer(step_text):
        candidate = m.group(1)
        if any(candidate.startswith(p) for p in cli_prefixes):
            continue
        # Filter URL-y things.
        if candidate.startswith(("http://", "https://")):
            continue
        if candidate not in seen:
            seen.add(candidate)
            paths.append(candidate)
    return paths


def _resolve_repo_paths(project_dir: Path, session) -> list[tuple[Path, str | None]]:
    """Find local clone paths for every code repo bound to this session.

    Reuses the same lookup as prep.py — single source of truth for the
    project.yaml.repos[<slug>].local mapping. Returns `(clone, path_prefix)`
    pairs so callers can resolve plan paths at both the clone root and the
    prefix-rooted sub-tree.
    """
    from tripwire.cli.session import _resolve_clone_path

    paths_: list[tuple[Path, str | None]] = []
    for rb in session.repos:
        clone = _resolve_clone_path(project_dir, rb.repo)
        if clone is not None:
            paths_.append((clone, rb.path_prefix))
    return paths_


def _check_target_existence(
    file_paths: list[str],
    repo_clones: list[tuple[Path, str | None]],
    classification: Literal["create", "modify"],
    step_title: str,
) -> list[PlanCheckResult]:
    """For each file path, check existence across all repo clone roots.

    A path is considered "exists" if it resolves to an existing file or
    directory under any of the repo clones — at the clone root OR at
    `<clone>/<path_prefix>` when the binding declares a prefix.
    """
    findings: list[PlanCheckResult] = []
    for fp in file_paths:
        exists_anywhere = any(
            (clone / fp).exists()
            or (prefix is not None and (clone / prefix / fp).exists())
            for clone, prefix in repo_clones
        )
        if classification == "create" and exists_anywhere:
            findings.append(
                PlanCheckResult(
                    code="plan/create_target_exists",
                    severity="warning",
                    message=(
                        f"{step_title} says create `{fp}` but the file "
                        "already exists. Plan may be obsolete in this step."
                    ),
                    location=fp,
                )
            )
        elif classification == "modify" and not exists_anywhere:
            findings.append(
                PlanCheckResult(
                    code="plan/modify_target_missing",
                    severity="warning",
                    message=(
                        f"{step_title} says modify `{fp}` but the file "
                        "does not exist in any code repo."
                    ),
                    location=fp,
                )
            )
    return findings


def validate_plan(project_dir: Path, session_id: str) -> PlanReport:
    """Run every plan check and return the aggregate report."""
    report = PlanReport(session_id=session_id)

    plan_path = session_plan_path(project_dir, session_id)
    if not plan_path.is_file():
        report.errors.append(
            PlanCheckResult(
                code="plan/missing",
                severity="error",
                message=f"plan.md not found at {plan_path}",
                location=str(plan_path),
            )
        )
        return report

    plan_body = plan_path.read_text(encoding="utf-8")

    # Check 2: every [[ref]] resolves.
    concepts = extract_plan_concepts(project_dir, session_id)
    for entry in concepts:
        if not entry.exists:
            report.errors.append(
                PlanCheckResult(
                    code="plan/unresolved_ref",
                    severity="error",
                    message=(
                        f"plan references `[[{entry.id}]]` but no node "
                        f"file at {entry.node_path}"
                    ),
                    location=str(plan_path.relative_to(project_dir)),
                )
            )

    # Checks 3 + 4: heuristic file-target checks per step.
    try:
        session = load_session(project_dir, session_id)
    except FileNotFoundError:
        # plan.md exists but session.yaml doesn't — odd state, skip the
        # repo-aware checks. Caller already has the unresolved-ref data.
        return report
    repo_clones = _resolve_repo_paths(project_dir, session)
    if not repo_clones:
        # No clones registered — heuristic checks would be vacuous.
        return report

    for step in _split_into_steps(plan_body):
        classification = _classify_step(step)
        if classification == "other":
            continue
        first_line = step.splitlines()[0] if step.splitlines() else "(unnamed step)"
        step_title = first_line.lstrip("# ").strip()
        file_paths = _extract_paths(step)
        if not file_paths:
            continue
        report.warnings.extend(
            _check_target_existence(file_paths, repo_clones, classification, step_title)
        )

    return report


def _render_markdown(report: PlanReport) -> str:
    """Markdown output — default, agent-readable."""
    lines: list[str] = [f"# Plan validation — {report.session_id}", ""]
    if report.exit_code == 0:
        lines.append("**Verdict:** ✓ no issues found")
        return "\n".join(lines) + "\n"
    bits = []
    if report.errors:
        bits.append(
            f"{len(report.errors)} error" + ("s" if len(report.errors) != 1 else "")
        )
    if report.warnings:
        bits.append(
            f"{len(report.warnings)} warning"
            + ("s" if len(report.warnings) != 1 else "")
        )
    lines.append(f"**Verdict:** ⚠ {' , '.join(bits)}")
    lines.append("")
    if report.errors:
        lines.append("## Errors")
        for r in report.errors:
            loc = f" — `{r.location}`" if r.location else ""
            lines.append(f"- `{r.code}`{loc} — {r.message}")
        lines.append("")
    if report.warnings:
        lines.append("## Warnings")
        for r in report.warnings:
            loc = f" — `{r.location}`" if r.location else ""
            lines.append(f"- `{r.code}`{loc} — {r.message}")
        lines.append("")
    if report.warnings or report.errors:
        lines.append(
            "**Suggested action:** PM should update the plan to reflect "
            "current repo state before queueing."
        )
    return "\n".join(lines) + "\n"


@click.command(name="validate-plan")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.cwd(),
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format. Markdown text default; JSON for machine pipelines.",
)
def validate_plan_cmd(
    session_id: str,
    project_dir: Path,
    output_format: str,
) -> None:
    """Validate a session's plan.md against current repo state.

    Catches plans that have gone obsolete: unresolved `[[ref]]`s, "create
    X" steps where X already exists, "modify X" steps where X is missing.
    Run before `tripwire session queue` to avoid burning agent time on
    salvage work.

    Exit codes: 0 = clean, 1 = warnings only, 2 = errors.
    """
    report = validate_plan(project_dir.expanduser().resolve(), session_id)
    if output_format == "json":
        click.echo(report.to_json())
    else:
        click.echo(_render_markdown(report))
    raise click.exceptions.Exit(report.exit_code)
