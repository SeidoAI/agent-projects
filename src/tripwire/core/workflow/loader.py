"""Read-only loader for ``<project>/workflow.yaml``.

Parses the raw YAML into the :class:`WorkflowSpec` typed tree. Never
mutates state — the file is read, normalised into dataclasses, and
returned. Structural anomalies that can't be expressed in the typed
tree (e.g. a status with both ``terminal: true`` and ``next:``) are
recorded as :class:`WorkflowFinding` entries on
``WorkflowSpec.load_findings`` and surfaced through
:func:`validate_workflow_spec`.

The file is optional: a missing ``workflow.yaml`` returns an empty
:class:`WorkflowSpec`. v0.9 ships with ``coding-session`` defined; new
projects pick up the default through ``tripwire init`` (a sibling step
plants ``workflow.yaml`` from the packaged template).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tripwire.core.workflow.schema import (
    ConditionalBranch,
    NextSpec,
    Predicate,
    Workflow,
    WorkflowArtifactRef,
    WorkflowCrossLink,
    WorkflowFinding,
    WorkflowRoute,
    WorkflowRouteControls,
    WorkflowRouteEmits,
    WorkflowSpec,
    WorkflowStatus,
    WorkflowStatusArtifacts,
    WorkflowWorkStep,
)

WORKFLOW_FILENAME = "workflow.yaml"


def workflow_path(project_dir: Path) -> Path:
    """Return ``<project_dir>/workflow.yaml`` (may not exist)."""
    return project_dir / WORKFLOW_FILENAME


def load_workflows(project_dir: Path) -> WorkflowSpec:
    """Parse ``<project_dir>/workflow.yaml`` into a :class:`WorkflowSpec`.

    Returns an empty spec if the file is missing or empty. Raises
    :class:`yaml.YAMLError` on a parse failure (callers route through
    the validator, which catches and reports).
    """
    path = workflow_path(project_dir)
    if not path.is_file():
        return WorkflowSpec()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return parse_workflow_spec(raw)


def parse_workflow_spec(raw: Any) -> WorkflowSpec:
    """Normalise raw YAML data into a :class:`WorkflowSpec`.

    Exposed separately from :func:`load_workflows` so unit tests and the
    validator integration can construct specs from in-memory payloads
    without round-tripping through disk.
    """
    if not isinstance(raw, dict):
        return WorkflowSpec()
    workflows_block = raw.get("workflows") or {}
    if not isinstance(workflows_block, dict):
        return WorkflowSpec()

    workflows: dict[str, Workflow] = {}
    load_findings: list[WorkflowFinding] = []
    for wf_id, wf_raw in workflows_block.items():
        if not isinstance(wf_id, str):
            continue
        if not isinstance(wf_raw, dict):
            continue
        workflow, wf_findings = _parse_workflow(wf_id, wf_raw)
        workflows[wf_id] = workflow
        load_findings.extend(wf_findings)
    return WorkflowSpec(workflows=workflows, load_findings=load_findings)


def _parse_workflow(wf_id: str, raw: dict) -> tuple[Workflow, list[WorkflowFinding]]:
    actor = str(raw.get("actor", "")) or ""
    trigger = str(raw.get("trigger", "")) or ""
    brief_raw = raw.get("brief-description", raw.get("brief_description"))
    brief_description = (
        str(brief_raw).strip()
        if isinstance(brief_raw, str) and brief_raw.strip()
        else None
    )
    findings: list[WorkflowFinding] = []
    if "stations" in raw:
        findings.append(
            WorkflowFinding(
                code="workflow/stale_stations_key",
                workflow=wf_id,
                status=None,
                message=(
                    "workflow.yaml uses stale `stations:`; use `statuses:` instead"
                ),
            )
        )
    statuses_raw = raw.get("statuses") or []
    statuses: list[WorkflowStatus] = []
    if not isinstance(statuses_raw, list):
        return (
            Workflow(
                id=wf_id,
                actor=actor,
                trigger=trigger,
                statuses=[],
                brief_description=brief_description,
            ),
            findings,
        )

    for entry in statuses_raw:
        if not isinstance(entry, dict):
            continue
        status, sfindings = _parse_status(wf_id, entry)
        statuses.append(status)
        findings.extend(sfindings)
    routes = _parse_routes(wf_id, raw.get("routes"), statuses)
    return (
        Workflow(
            id=wf_id,
            actor=actor,
            trigger=trigger,
            statuses=statuses,
            routes=routes,
            brief_description=brief_description,
        ),
        findings,
    )


def _parse_status(
    wf_id: str, raw: dict
) -> tuple[WorkflowStatus, list[WorkflowFinding]]:
    sid = str(raw.get("id", "")) or "<unknown>"
    findings: list[WorkflowFinding] = []
    has_terminal = bool(raw.get("terminal"))
    next_raw = raw.get("next")
    has_next = next_raw is not None

    if has_terminal and has_next:
        findings.append(
            WorkflowFinding(
                code="workflow/terminal_with_next",
                workflow=wf_id,
                status=sid,
                message=(
                    f"status {sid!r} declares both `terminal: true` and "
                    f"`next:` — a status is either terminal or transitions, "
                    f"never both"
                ),
            )
        )
        nxt = NextSpec(kind="terminal")
    elif has_terminal:
        nxt = NextSpec(kind="terminal")
    elif has_next:
        nxt, parse_findings = _parse_next(wf_id, sid, next_raw)
        findings.extend(parse_findings)
    else:
        # No terminal AND no next — treat as terminal=False but no next;
        # the validator surfaces this through the no-terminal-status
        # check at the workflow level. Carry the empty next as a single
        # NextSpec pointing at the status itself sentinel… no, keep it
        # honest and emit a load finding.
        findings.append(
            WorkflowFinding(
                code="workflow/missing_next_or_terminal",
                workflow=wf_id,
                status=sid,
                message=(
                    f"status {sid!r} declares neither `next:` nor "
                    f"`terminal: true` — every status must do exactly one"
                ),
            )
        )
        nxt = NextSpec(kind="terminal")

    return (
        WorkflowStatus(
            id=sid,
            next=nxt,
            prompt_checks=_str_list(raw.get("prompt_checks")),
            tripwires=_str_list(raw.get("tripwires")),
            heuristics=_str_list(raw.get("heuristics")),
            jit_prompts=_str_list(raw.get("jit_prompts")),
            artifacts=_parse_artifacts(raw.get("artifacts")),
            work_steps=_parse_work_steps(raw.get("work_steps")),
            cross_links=_parse_cross_links(raw.get("cross_links")),
        ),
        findings,
    )


def _parse_cross_links(value: Any) -> list[WorkflowCrossLink]:
    if not isinstance(value, list):
        return []
    out: list[WorkflowCrossLink] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        wf = str(entry.get("workflow", "")).strip()
        st = str(entry.get("status", "")).strip()
        if not wf or not st:
            continue
        kind_raw = str(entry.get("kind") or "triggers").strip()
        kind = kind_raw if kind_raw in ("triggers", "triggered_by") else "triggers"
        label_raw = entry.get("label")
        label = str(label_raw).strip() if label_raw is not None else None
        sub = bool(entry.get("pm_subagent_dispatch", False))
        out.append(
            WorkflowCrossLink(
                workflow=wf,
                status=st,
                label=label,
                kind=kind,  # type: ignore[arg-type]
                pm_subagent_dispatch=sub,
            )
        )
    return out


def _parse_work_steps(value: Any) -> list[WorkflowWorkStep]:
    if not isinstance(value, list):
        return []
    out: list[WorkflowWorkStep] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        ws_id = str(entry.get("id", "")).strip()
        if not ws_id:
            continue
        out.append(
            WorkflowWorkStep(
                id=ws_id,
                actor=str(entry.get("actor", "")).strip(),
                label=str(entry.get("label") or ws_id).strip(),
                skills=_str_list(entry.get("skills")),
            )
        )
    return out


def _parse_next(
    wf_id: str, status_id: str, raw: Any
) -> tuple[NextSpec, list[WorkflowFinding]]:
    findings: list[WorkflowFinding] = []
    if isinstance(raw, str):
        return NextSpec(kind="single", single=raw), findings
    if not isinstance(raw, list):
        findings.append(
            WorkflowFinding(
                code="workflow/invalid_next_shape",
                workflow=wf_id,
                status=status_id,
                message=(
                    f"status {status_id!r} `next:` must be a status id "
                    f"or a list of conditional branches; got "
                    f"{type(raw).__name__}"
                ),
            )
        )
        return NextSpec(kind="single", single=""), findings

    branches: list[ConditionalBranch] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if "if" in entry and "then" in entry:
            try:
                pred = Predicate.parse(str(entry["if"]))
            except ValueError as exc:
                findings.append(
                    WorkflowFinding(
                        code="workflow/invalid_predicate",
                        workflow=wf_id,
                        status=status_id,
                        message=str(exc),
                    )
                )
                continue
            branches.append(ConditionalBranch(predicate=pred, then=str(entry["then"])))
        elif "else" in entry:
            branches.append(ConditionalBranch(predicate=None, then=str(entry["else"])))
        else:
            findings.append(
                WorkflowFinding(
                    code="workflow/invalid_branch",
                    workflow=wf_id,
                    status=status_id,
                    message=(
                        f"status {status_id!r} conditional branch must "
                        f"declare `if:`+`then:` or `else:`; got {entry!r}"
                    ),
                )
            )
    return NextSpec(kind="conditional", conditional=branches), findings


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, (str, int))]


def _parse_artifacts(value: Any) -> WorkflowStatusArtifacts:
    if not isinstance(value, dict):
        return WorkflowStatusArtifacts()
    return WorkflowStatusArtifacts(
        produces=_parse_artifact_refs(value.get("produces")),
        consumes=_parse_artifact_refs(value.get("consumes")),
    )


def _parse_artifact_refs(value: Any) -> list[WorkflowArtifactRef]:
    if not isinstance(value, list):
        return []
    out: list[WorkflowArtifactRef] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        artifact_id = str(entry.get("id", "")).strip()
        label = str(entry.get("label", "")).strip()
        if not artifact_id:
            continue
        path = entry.get("path")
        out.append(
            WorkflowArtifactRef(
                id=artifact_id,
                label=label or artifact_id,
                path=str(path) if path else None,
            )
        )
    return out


def _parse_routes(
    wf_id: str, value: Any, statuses: list[WorkflowStatus]
) -> list[WorkflowRoute]:
    if not isinstance(value, list):
        return []
    status_index = {status.id: idx for idx, status in enumerate(statuses)}
    routes: list[WorkflowRoute] = []
    for idx, entry in enumerate(value):
        if not isinstance(entry, dict):
            continue
        from_ref = str(entry.get("from", "")).strip()
        to_ref = str(entry.get("to", "")).strip()
        route_id = str(entry.get("id") or f"{from_ref or 'unknown'}-to-{to_ref or idx}")
        kind = str(entry.get("kind") or "").strip()
        if kind not in {"forward", "return", "loop", "side", "terminal"}:
            kind = _classify_route_kind(from_ref, to_ref, status_index)
        label = str(entry.get("label") or entry.get("command") or route_id).strip()
        command = entry.get("command")
        trigger = entry.get("trigger")
        routes.append(
            WorkflowRoute(
                id=route_id,
                actor=str(entry.get("actor", "")).strip(),
                from_ref=from_ref,
                to_ref=to_ref,
                kind=kind,  # type: ignore[arg-type]
                label=label,
                trigger=str(trigger).strip() if trigger else None,
                command=str(command).strip() if command else None,
                controls=_parse_route_controls(entry.get("controls")),
                signals=_str_list(entry.get("signals")),
                skills=_str_list(entry.get("skills")),
                emits=_parse_route_emits(entry.get("emits")),
            )
        )
    return routes


def _classify_route_kind(
    from_ref: str, to_ref: str, status_index: dict[str, int]
) -> str:
    if to_ref.startswith("sink:"):
        return "terminal"
    if from_ref == to_ref and from_ref:
        return "loop"
    from_idx = status_index.get(from_ref)
    to_idx = status_index.get(to_ref)
    if from_idx is None or to_idx is None:
        return "side"
    if to_idx > from_idx:
        return "forward"
    if to_idx < from_idx:
        return "return"
    return "side"


def _parse_route_controls(value: Any) -> WorkflowRouteControls:
    if not isinstance(value, dict):
        return WorkflowRouteControls()
    return WorkflowRouteControls(
        tripwires=_str_list(value.get("tripwires")),
        heuristics=_str_list(value.get("heuristics")),
        jit_prompts=_str_list(value.get("jit_prompts")),
        prompt_checks=_str_list(value.get("prompt_checks")),
    )


def _parse_route_emits(value: Any) -> WorkflowRouteEmits:
    if not isinstance(value, dict):
        return WorkflowRouteEmits()
    return WorkflowRouteEmits(
        artifacts=_parse_artifact_refs(value.get("artifacts")),
        events=_str_list(value.get("events")),
        comments=_str_list(value.get("comments")),
        status_changes=_str_list(value.get("status_changes")),
    )


__all__ = [
    "WORKFLOW_FILENAME",
    "load_workflows",
    "parse_workflow_spec",
    "workflow_path",
]
