"""Strict pre-spawn checks (v0.7.9 §A6).

``tripwire session check`` and ``tripwire session spawn`` both call
:func:`strict_check`. Every result with ``severity="error"`` blocks the
spawn gate. There is **no bypass flag** — the only escape valve is to
fix the underlying condition. The 8 tripwires below were derived from
real failure modes observed during the 2026-04-25 batch (see
``docs/specs/2026-04-25-v079-handoff.md`` §A6).

Each tripwire is one function returning ``StrictCheckResult | None``;
``strict_check`` walks them and aggregates results. Adding a new
tripwire = add a function + dispatch entry + test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tripwire.core.session_store import load_session
from tripwire.core.spawn_config import load_resolved_spawn_config
from tripwire.core.store import load_issue, load_project
from tripwire.models.session import AgentSession


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class StrictCheckResult:
    """One strict-check finding.

    ``error_code`` is namespaced ``check/<slug>``. ``severity="error"``
    blocks ``session spawn``; ``severity="warning"`` is informational.
    """

    error_code: str
    severity: Severity
    message: str
    fix_hint: str | None = None


def any_blocking_error(results: list[StrictCheckResult]) -> bool:
    """Return True iff any result has ``severity="error"``."""
    return any(r.severity == "error" for r in results)


# ---------------------------------------------------------------------------
# Tripwire #1 — check/plan_unfilled
# ---------------------------------------------------------------------------


# Substrings the shipped plan.md.j2 emits before PM fills it in. Catches
# the cases where ``<…>`` placeholders have been deleted but the
# narrative scaffolding sentences are still present.
_PLAN_SCAFFOLD_STRINGS = (
    "What to read, what to understand, what assumptions to verify",
    "What to build, in what order",
    "How you will check your own work before declaring done",
    "What is this session trying to achieve, in one paragraph",
    "Things I could do but will NOT in this session",
    "Decision: <what>. Rationale: <why>",
    "Risk: <what could go wrong>. Mitigation: <plan B>",
)

# Body floor below which the plan is treated as unfilled regardless of
# placeholders. 200 chars is roughly two short paragraphs — enough for
# even a tiny session to put down real intent.
_PLAN_BODY_MIN_CHARS = 200


def _check_plan_unfilled(
    project_dir: Path, session: AgentSession
) -> StrictCheckResult | None:
    plan_path = project_dir / "sessions" / session.id / "plan.md"
    if not plan_path.is_file():
        return StrictCheckResult(
            error_code="check/plan_unfilled",
            severity="error",
            message=f"plan.md missing at {plan_path.relative_to(project_dir)}",
            fix_hint="Run `tripwire session scaffold` then fill in plan.md",
        )
    text = plan_path.read_text(encoding="utf-8")

    # Placeholder syntax `<word>` (but not legitimate angle-bracket prose
    # like XML examples; the heuristic looks for short slug-y placeholders).
    placeholder_pattern = re.compile(r"<[A-Za-z][A-Za-z0-9_./-]{0,40}>")
    if placeholder_pattern.search(text):
        return StrictCheckResult(
            error_code="check/plan_unfilled",
            severity="error",
            message="plan.md still contains placeholder syntax (e.g. `<session-id>`)",
            fix_hint="Replace every `<…>` placeholder with real content",
        )

    for needle in _PLAN_SCAFFOLD_STRINGS:
        if needle in text:
            return StrictCheckResult(
                error_code="check/plan_unfilled",
                severity="error",
                message=(
                    f"plan.md still contains scaffold-template prose: "
                    f"{needle!r}"
                ),
                fix_hint="Replace scaffold prose with the real plan content",
            )

    # Body length floor — strip leading heading + frontmatter to count
    # narrative chars only.
    body = re.sub(r"(?m)^#.*$", "", text)
    body = re.sub(r"\s+", " ", body).strip()
    if len(body) < _PLAN_BODY_MIN_CHARS:
        return StrictCheckResult(
            error_code="check/plan_unfilled",
            severity="error",
            message=(
                f"plan.md body is too short ({len(body)} chars; "
                f"minimum {_PLAN_BODY_MIN_CHARS}). Likely a stub."
            ),
            fix_hint="Write out goal/approach/verification phases",
        )

    return None


# ---------------------------------------------------------------------------
# Tripwire #2 — check/checklist_unfilled
# ---------------------------------------------------------------------------


def _check_checklist_unfilled(
    project_dir: Path, session: AgentSession
) -> StrictCheckResult | None:
    path = project_dir / "sessions" / session.id / "task-checklist.md"
    if not path.is_file():
        # task-checklist is owned by the execution agent (produced_at:
        # in_progress in the shipped manifest) — its absence pre-spawn is
        # normal. Don't fire here.
        return None
    text = path.read_text(encoding="utf-8")

    # Parse the markdown table rows (skip header + separator).
    rows: list[list[str]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        if cells == ["#", "Task", "Status", "Comments"]:
            continue
        if all(set(c) <= set("-") for c in cells if c):
            continue  # separator row
        rows.append(cells)

    if not rows:
        # No table at all — treat as scaffold-template only.
        return StrictCheckResult(
            error_code="check/checklist_unfilled",
            severity="error",
            message="task-checklist.md has no task rows",
            fix_hint="Add at least one task row with real status/comment",
        )

    # All rows pending AND every Comments cell is empty/em-dash → unfilled.
    EMPTY_COMMENTS = {"", "—", "-", "–"}
    statuses = [r[2].lower() if len(r) > 2 else "" for r in rows]
    comments = [r[3] if len(r) > 3 else "" for r in rows]
    all_pending = all(s == "pending" for s in statuses)
    no_body = all(c.strip() in EMPTY_COMMENTS for c in comments)
    if all_pending and no_body:
        return StrictCheckResult(
            error_code="check/checklist_unfilled",
            severity="error",
            message=(
                "task-checklist.md is scaffold-template only "
                "(all rows pending, no comments)"
            ),
            fix_hint=(
                "Either advance one task to `done`/`in_progress` or add "
                "real comments before queueing"
            ),
        )

    return None


# ---------------------------------------------------------------------------
# Tripwire #3 — check/verification_unfilled
# ---------------------------------------------------------------------------


_CHECKBOX_RE = re.compile(r"-\s*\[(?P<state>[ xX])\]\s*(?P<rest>.*)")


def _check_verification_unfilled(
    project_dir: Path, session: AgentSession
) -> StrictCheckResult | None:
    path = project_dir / "sessions" / session.id / "verification-checklist.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")

    items: list[tuple[str, str]] = []
    for line in text.splitlines():
        m = _CHECKBOX_RE.search(line)
        if m:
            items.append((m.group("state"), m.group("rest")))

    if not items:
        # No checkboxes at all — verification template was deleted or
        # never written; this is a checklist_unfilled-class failure.
        return StrictCheckResult(
            error_code="check/verification_unfilled",
            severity="error",
            message="verification-checklist.md has no checkbox items",
            fix_hint="Restore the verification-checklist template content",
        )

    all_unchecked = all(state == " " for state, _ in items)
    # "Evidence" heuristic: any item whose body contains a dash-space
    # ("— …" / "- …") with content beyond a few words is treated as
    # evidence. Also any line containing "see " or "verified" in body.
    def _has_evidence(rest: str) -> bool:
        rest = rest.strip()
        if " — " in rest or " - " in rest:
            tail = rest.split(" — ", 1)[-1].split(" - ", 1)[-1].strip()
            if len(tail) >= 5:
                return True
        return any(kw in rest.lower() for kw in ("see ", "verified", "commit "))

    no_evidence = not any(_has_evidence(rest) for _, rest in items)

    if all_unchecked and no_evidence:
        return StrictCheckResult(
            error_code="check/verification_unfilled",
            severity="error",
            message=(
                "verification-checklist.md is scaffold-only "
                "(all unchecked, no evidence noted)"
            ),
            fix_hint=(
                "Mark known-passing items `[x]` with evidence, or note "
                "expected evidence inline (e.g. `- [ ] X — see PR #123`)"
            ),
        )

    return None


# ---------------------------------------------------------------------------
# Tripwire #4 — check/repos_overlap
# ---------------------------------------------------------------------------


def _check_repos_overlap(
    project_dir: Path, session: AgentSession
) -> StrictCheckResult | None:
    """Detect today's bug: session.repos[i] resolves to project_dir.

    The framework's PT worktree is always cut from project_dir; if a
    session.repos entry's local clone path also points at project_dir,
    spawn double-creates the worktree at the same path. Block it here so
    the operator fixes the project.yaml / session.yaml instead of hitting
    the failure 30 seconds into spawn.
    """
    try:
        project = load_project(project_dir)
    except Exception:
        return None
    if not project.repos:
        return None

    project_resolved = project_dir.expanduser().resolve()
    for rb in session.repos:
        repo_cfg = project.repos.get(rb.repo) if isinstance(project.repos, dict) else None
        if repo_cfg is None:
            continue
        local = getattr(repo_cfg, "local", None)
        if local is None:
            continue
        try:
            clone_resolved = Path(local).expanduser().resolve()
        except OSError:
            continue
        if clone_resolved == project_resolved:
            return StrictCheckResult(
                error_code="check/repos_overlap",
                severity="error",
                message=(
                    f"session.repos[{rb.repo}] resolves to project_dir "
                    f"({project_resolved}); spawn would double-create the "
                    f"worktree"
                ),
                fix_hint=(
                    f"Remove the {rb.repo} entry from session.repos — the "
                    f"project-tracking worktree already covers project_dir"
                ),
            )
    return None


# ---------------------------------------------------------------------------
# Tripwire #5 — check/no_repos
# ---------------------------------------------------------------------------


def _check_no_repos(
    project_dir: Path, session: AgentSession
) -> StrictCheckResult | None:
    if not session.repos:
        return StrictCheckResult(
            error_code="check/no_repos",
            severity="error",
            message="session.repos is empty",
            fix_hint=(
                "Add at least one repo to session.yaml under `repos:` "
                "(format: `- repo: org/name\\n  base_branch: main`)"
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Tripwire #6 — check/no_issues
# ---------------------------------------------------------------------------


def _check_no_issues(
    project_dir: Path, session: AgentSession
) -> StrictCheckResult | None:
    if not session.issues:
        return StrictCheckResult(
            error_code="check/no_issues",
            severity="error",
            message="session has no issues attached — no traceability",
            fix_hint=(
                "Add at least one issue key to session.yaml under `issues:`"
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Tripwire #7 — check/missing_template (warning)
# ---------------------------------------------------------------------------


# Match `path/to/file.md` (with or without backticks) — must end in a
# recognised extension. Anchored on `\b` so we don't accidentally match
# bare KUI-1 keys etc.
_DOD_PATH_RE = re.compile(
    r"`?(?P<path>[A-Za-z0-9_./\-]+\.(?:md|yaml|yml|json|txt))`?"
)


def _check_missing_template(
    project_dir: Path, session: AgentSession
) -> StrictCheckResult | None:
    """Warn if any issue's DoD lists artifact paths with no template.

    DoD entries that reference `developer.md`, `verified.md`, `plan.md`,
    etc. expect a corresponding ``.j2`` template under
    ``templates/artifacts/`` or ``templates/issue_artifacts/``. A DoD
    referencing a path with no template suggests either a typo or a
    yet-to-be-shipped template — surface as a warning so PM can decide.

    Warn-only by spec — see §A6 #7.
    """
    template_roots = [
        project_dir / "templates" / "artifacts",
        project_dir / "templates" / "issue_artifacts",
    ]

    # Collect available templates (basename without .j2).
    available: set[str] = set()
    for root in template_roots:
        if not root.is_dir():
            continue
        for tpl in root.iterdir():
            if tpl.suffix == ".j2":
                # plan.md.j2 → plan.md
                available.add(tpl.name.removesuffix(".j2"))
            else:
                available.add(tpl.name)

    missing: list[str] = []
    for issue_key in session.issues:
        try:
            issue = load_issue(project_dir, issue_key)
        except FileNotFoundError:
            continue
        body = issue.body or ""
        # Look at the Definition of Done section specifically.
        m = re.search(
            r"##\s+Definition of Done(.*?)(?=\n##\s|\Z)",
            body,
            re.DOTALL | re.IGNORECASE,
        )
        if not m:
            continue
        dod = m.group(1)
        for path_match in _DOD_PATH_RE.finditer(dod):
            path = path_match.group("path")
            basename = Path(path).name
            if basename not in available:
                missing.append(f"{issue_key}: {path}")

    if missing:
        return StrictCheckResult(
            error_code="check/missing_template",
            severity="warning",
            message=(
                "issue DoD references artifact paths with no matching "
                "template under templates/{artifacts,issue_artifacts}/: "
                + ", ".join(missing)
            ),
            fix_hint=(
                "Either add the .j2 template, fix the DoD path, or "
                "ignore — this is a warning only"
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Tripwire #8 — check/invalid_effort
# ---------------------------------------------------------------------------


# Hardcoded model→effort matrix. v0.7.10's routing.yaml will replace
# this with a data-driven table. Keys are normalised model names; values
# are the set of efforts each accepts.
#
# The known shape today: opus accepts every effort tier (xhigh is opus-
# only), sonnet tops out at high, haiku tops out at medium.
_MODEL_EFFORT_MATRIX: dict[str, frozenset[str]] = {
    "opus": frozenset({"low", "medium", "high", "xhigh"}),
    "sonnet": frozenset({"low", "medium", "high"}),
    "haiku": frozenset({"low", "medium"}),
}


def _normalise_model(name: str) -> str:
    """Map ``claude-opus-4-7`` / ``opus-4.7`` / ``opus`` → ``opus``."""
    name = name.lower()
    for known in _MODEL_EFFORT_MATRIX:
        if known in name:
            return known
    return name


def _check_invalid_effort(
    project_dir: Path, session: AgentSession
) -> StrictCheckResult | None:
    try:
        resolved = load_resolved_spawn_config(project_dir, session=session)
    except Exception:
        return None
    model = _normalise_model(resolved.config.model)
    effort = resolved.config.effort.lower()

    accepted = _MODEL_EFFORT_MATRIX.get(model)
    if accepted is None:
        # Unknown model — can't validate against the hardcoded matrix.
        # Don't block; v0.7.10's routing.yaml will be the data-driven
        # source of truth.
        return None
    if effort not in accepted:
        return StrictCheckResult(
            error_code="check/invalid_effort",
            severity="error",
            message=(
                f"spawn_config: effort {effort!r} is not valid for "
                f"model {resolved.config.model!r} (model accepts: "
                f"{sorted(accepted)})"
            ),
            fix_hint=(
                "Lower the effort to one of the accepted values, or "
                "switch to a model that supports the desired effort"
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


# Order matters only for output; aggregation is set-based.
_TRIPWIRES = (
    _check_no_repos,
    _check_no_issues,
    _check_repos_overlap,
    _check_plan_unfilled,
    _check_checklist_unfilled,
    _check_verification_unfilled,
    _check_missing_template,
    _check_invalid_effort,
)


def strict_check(
    project_dir: Path, session_id: str
) -> list[StrictCheckResult]:
    """Run every strict tripwire against ``session_id``.

    Raises :class:`FileNotFoundError` if the session doesn't exist.
    Returns the list of all results (errors and warnings); callers use
    :func:`any_blocking_error` to decide whether to refuse spawn.
    """
    session = load_session(project_dir, session_id)
    results: list[StrictCheckResult] = []
    for tw in _TRIPWIRES:
        try:
            result = tw(project_dir, session)
        except Exception as exc:  # pragma: no cover — defensive
            # A tripwire crashing must not silently let spawn through.
            # Surface it as an error with a synthetic code so the operator
            # sees the failure, with the original tripwire's name in the
            # message for debugging.
            results.append(
                StrictCheckResult(
                    error_code="check/internal_error",
                    severity="error",
                    message=(
                        f"strict-check tripwire {tw.__name__} crashed: {exc!r}"
                    ),
                    fix_hint="File a bug; this is an internal tripwire failure",
                )
            )
            continue
        if result is not None:
            results.append(result)
    return results
