"""Read-only loader for ``<project>/workflow.yaml``.

Parses the raw YAML into the :class:`WorkflowSpec` typed tree. Never
mutates state — the file is read, normalised into dataclasses, and
returned. Structural anomalies that can't be expressed in the typed
tree (e.g. a station with both ``terminal: true`` and ``next:``) are
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
    Station,
    Workflow,
    WorkflowFinding,
    WorkflowSpec,
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
    stations_raw = raw.get("stations") or []
    findings: list[WorkflowFinding] = []
    stations: list[Station] = []
    if not isinstance(stations_raw, list):
        return Workflow(id=wf_id, actor=actor, trigger=trigger, stations=[]), findings

    for entry in stations_raw:
        if not isinstance(entry, dict):
            continue
        station, sfindings = _parse_station(wf_id, entry)
        stations.append(station)
        findings.extend(sfindings)
    return Workflow(id=wf_id, actor=actor, trigger=trigger, stations=stations), findings


def _parse_station(wf_id: str, raw: dict) -> tuple[Station, list[WorkflowFinding]]:
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
                station=sid,
                message=(
                    f"station {sid!r} declares both `terminal: true` and "
                    f"`next:` — a station is either terminal or transitions, "
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
        # the validator surfaces this through the no-terminal-station
        # check at the workflow level. Carry the empty next as a single
        # NextSpec pointing at the station itself sentinel… no, keep it
        # honest and emit a load finding.
        findings.append(
            WorkflowFinding(
                code="workflow/missing_next_or_terminal",
                workflow=wf_id,
                station=sid,
                message=(
                    f"station {sid!r} declares neither `next:` nor "
                    f"`terminal: true` — every station must do exactly one"
                ),
            )
        )
        nxt = NextSpec(kind="terminal")

    return (
        Station(
            id=sid,
            next=nxt,
            prompt_checks=_str_list(raw.get("prompt_checks")),
            validators=_str_list(raw.get("validators")),
            tripwires=_str_list(raw.get("tripwires")),
        ),
        findings,
    )


def _parse_next(
    wf_id: str, station_id: str, raw: Any
) -> tuple[NextSpec, list[WorkflowFinding]]:
    findings: list[WorkflowFinding] = []
    if isinstance(raw, str):
        return NextSpec(kind="single", single=raw), findings
    if not isinstance(raw, list):
        findings.append(
            WorkflowFinding(
                code="workflow/invalid_next_shape",
                workflow=wf_id,
                station=station_id,
                message=(
                    f"station {station_id!r} `next:` must be a station id "
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
                        station=station_id,
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
                    station=station_id,
                    message=(
                        f"station {station_id!r} conditional branch must "
                        f"declare `if:`+`then:` or `else:`; got {entry!r}"
                    ),
                )
            )
    return NextSpec(kind="conditional", conditional=branches), findings


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, (str, int))]


__all__ = [
    "WORKFLOW_FILENAME",
    "load_workflows",
    "parse_workflow_spec",
    "workflow_path",
]
