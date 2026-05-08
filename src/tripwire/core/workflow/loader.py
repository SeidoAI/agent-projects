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

# Recognized-key sets at every workflow.yaml level. Keep these in sync
# with the parser. Any key not in the set fires a `workflow/unknown_key`
# finding at load time. The check is deliberately name-blind — it
# surfaces stale shapes (e.g. an old `stations:` or `validators:` block
# from before a rename), forward-incompatible additions, and plain
# typos with one mechanism.
_RECOGNIZED_WORKFLOW_KEYS = frozenset(
    {"actor", "trigger", "brief-description", "brief_description", "statuses", "routes"}
)
_RECOGNIZED_STATUS_KEYS = frozenset(
    {
        "id",
        "next",
        "terminal",
        "prompt_checks",
        "tripwires",
        "heuristics",
        "jit_prompts",
        "artifacts",
        "work_steps",
        "cross_links",
    }
)
_RECOGNIZED_ROUTE_KEYS = frozenset(
    {
        "id",
        "actor",
        "command",
        "trigger",
        "signals",
        "from",
        "to",
        "kind",
        "label",
        "controls",
        "skills",
        "emits",
    }
)
_RECOGNIZED_CONTROLS_KEYS = frozenset(
    {"tripwires", "heuristics", "jit_prompts", "prompt_checks"}
)
_RECOGNIZED_CROSS_LINK_KEYS = frozenset(
    {"workflow", "status", "label", "kind", "pm_subagent_dispatch"}
)
_RECOGNIZED_ARTIFACTS_KEYS = frozenset({"produces", "consumes"})
_RECOGNIZED_ARTIFACT_REF_KEYS = frozenset({"id", "label", "path"})
_RECOGNIZED_WORK_STEP_KEYS = frozenset({"id", "actor", "label", "skills"})
_RECOGNIZED_EMITS_KEYS = frozenset(
    {"artifacts", "events", "comments", "status_changes"}
)
_RECOGNIZED_NEXT_BRANCH_KEYS = frozenset({"if", "then", "else"})


def workflow_path(project_dir: Path) -> Path:
    """Return ``<project_dir>/workflow.yaml`` (may not exist)."""
    return project_dir / WORKFLOW_FILENAME


def _audit_workflow_shape(wf_id: str, raw: dict) -> list[WorkflowFinding]:
    """Walk the raw workflow tree and emit ``workflow/unknown_key`` for
    every field the schema doesn't recognize at any level.

    Hard-migration policy: the loader is name-blind. It does not know
    what previous releases called any key — it only knows what v0.9.6's
    schema accepts. Stale shapes therefore surface as a single error
    code with the offending key in the message, alongside the
    recognized-key list so the author can correct the file.
    """
    findings: list[WorkflowFinding] = []

    def _emit(
        unknown: set[str],
        recognized: frozenset[str],
        context: str,
        *,
        status: str | None,
    ) -> None:
        for key in sorted(unknown):
            findings.append(
                WorkflowFinding(
                    code="workflow/unknown_key",
                    workflow=wf_id,
                    status=status,
                    message=(
                        f"unknown key {key!r} in {context}; recognized "
                        f"keys are {sorted(recognized)}"
                    ),
                )
            )

    if isinstance(raw, dict):
        _emit(
            set(raw.keys()) - _RECOGNIZED_WORKFLOW_KEYS,
            _RECOGNIZED_WORKFLOW_KEYS,
            f"workflow {wf_id!r}",
            status=None,
        )

        for status_raw in raw.get("statuses") or []:
            if not isinstance(status_raw, dict):
                continue
            sid = str(status_raw.get("id") or "<unknown>")
            _emit(
                set(status_raw.keys()) - _RECOGNIZED_STATUS_KEYS,
                _RECOGNIZED_STATUS_KEYS,
                f"status {sid!r}",
                status=sid,
            )

            for branch in _next_branches(status_raw.get("next")):
                _emit(
                    set(branch.keys()) - _RECOGNIZED_NEXT_BRANCH_KEYS,
                    _RECOGNIZED_NEXT_BRANCH_KEYS,
                    f"status {sid!r} `next:` branch",
                    status=sid,
                )

            artifacts_raw = status_raw.get("artifacts")
            if isinstance(artifacts_raw, dict):
                _emit(
                    set(artifacts_raw.keys()) - _RECOGNIZED_ARTIFACTS_KEYS,
                    _RECOGNIZED_ARTIFACTS_KEYS,
                    f"status {sid!r} `artifacts:`",
                    status=sid,
                )
                for bucket in ("produces", "consumes"):
                    for ref in artifacts_raw.get(bucket) or []:
                        if isinstance(ref, dict):
                            _emit(
                                set(ref.keys()) - _RECOGNIZED_ARTIFACT_REF_KEYS,
                                _RECOGNIZED_ARTIFACT_REF_KEYS,
                                f"status {sid!r} `artifacts.{bucket}` entry",
                                status=sid,
                            )

            for step in status_raw.get("work_steps") or []:
                if isinstance(step, dict):
                    _emit(
                        set(step.keys()) - _RECOGNIZED_WORK_STEP_KEYS,
                        _RECOGNIZED_WORK_STEP_KEYS,
                        f"status {sid!r} work-step",
                        status=sid,
                    )

            for link in status_raw.get("cross_links") or []:
                if isinstance(link, dict):
                    _emit(
                        set(link.keys()) - _RECOGNIZED_CROSS_LINK_KEYS,
                        _RECOGNIZED_CROSS_LINK_KEYS,
                        f"status {sid!r} cross-link",
                        status=sid,
                    )

        for route_raw in raw.get("routes") or []:
            if not isinstance(route_raw, dict):
                continue
            rid = str(route_raw.get("id") or "<unknown>")
            _emit(
                set(route_raw.keys()) - _RECOGNIZED_ROUTE_KEYS,
                _RECOGNIZED_ROUTE_KEYS,
                f"route {rid!r}",
                status=None,
            )

            controls_raw = route_raw.get("controls")
            if isinstance(controls_raw, dict):
                _emit(
                    set(controls_raw.keys()) - _RECOGNIZED_CONTROLS_KEYS,
                    _RECOGNIZED_CONTROLS_KEYS,
                    f"route {rid!r} `controls:`",
                    status=None,
                )

            emits_raw = route_raw.get("emits")
            if isinstance(emits_raw, dict):
                _emit(
                    set(emits_raw.keys()) - _RECOGNIZED_EMITS_KEYS,
                    _RECOGNIZED_EMITS_KEYS,
                    f"route {rid!r} `emits:`",
                    status=None,
                )
                for ref in emits_raw.get("artifacts") or []:
                    if isinstance(ref, dict):
                        _emit(
                            set(ref.keys()) - _RECOGNIZED_ARTIFACT_REF_KEYS,
                            _RECOGNIZED_ARTIFACT_REF_KEYS,
                            f"route {rid!r} `emits.artifacts` entry",
                            status=None,
                        )

    return findings


def _next_branches(value: Any) -> list[dict]:
    """Return dict branches under a status `next:` block (skip strings/non-dicts)."""
    if not isinstance(value, list):
        return []
    return [b for b in value if isinstance(b, dict)]


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
    findings.extend(_audit_workflow_shape(wf_id, raw))
    statuses_raw = raw.get("statuses")
    statuses: list[WorkflowStatus] = []
    # A workflow without statuses is a load error, not a silently-empty
    # workflow. Anyone hitting this from a stale shape (e.g. an old
    # `stations:` block from before the rename) gets the same generic
    # message — the loader never knew the old key name.
    if not statuses_raw:
        findings.append(
            WorkflowFinding(
                code="workflow/no_statuses_declared",
                workflow=wf_id,
                status=None,
                message=(
                    f"workflow {wf_id!r} declares no `statuses:`. Each "
                    f"workflow must list at least one status. If you're "
                    f"upgrading from an earlier release, the workflow.yaml "
                    f"shape is stale — regenerate via `tripwire init` or "
                    f"rewrite by hand to match `references/SCHEMA_WORKFLOW.md`."
                ),
            )
        )
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
