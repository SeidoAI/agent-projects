"""Read-only loader for ``<project>/workflow.yaml``.

Parses the raw YAML into the :class:`WorkflowSpec` typed tree. Never
mutates state — the file is read, normalised into dataclasses, and
returned. Structural anomalies that can't be expressed in the typed
tree (e.g. a status carrying an unrecognized key such as ``next:``)
are recorded as :class:`WorkflowFinding` entries on
``WorkflowSpec.load_findings`` and surfaced through
:func:`validate_workflow_spec`.

The file is optional: a missing ``workflow.yaml`` returns an empty
:class:`WorkflowSpec`. Every present file must declare
``workflow_schema_version: 1`` at the top; files that omit it are
rejected with ``workflow/missing_schema_version``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tripwire.core.workflow.schema import (
    Workflow,
    WorkflowArtifactRef,
    WorkflowCrossLink,
    WorkflowFinding,
    WorkflowInstanceShape,
    WorkflowRoute,
    WorkflowRouteControls,
    WorkflowRouteEmits,
    WorkflowRouteTrigger,
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
_RECOGNIZED_TOPLEVEL_KEYS = frozenset({"workflow_schema_version", "workflows"})
_RECOGNIZED_WORKFLOW_KEYS = frozenset(
    {
        "actor",
        "trigger",
        "brief-description",
        "brief_description",
        "statuses",
        "routes",
        "instance",
    }
)
_RECOGNIZED_INSTANCE_KEYS = frozenset(
    {
        "storage_path",
        "status_field",
        "status_enum",
        "required_fields",
        "instance_id_field",
        "singleton",
        "reference_only",
    }
)
_RECOGNIZED_STATUS_KEYS = frozenset(
    {
        "id",
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
        "preserve_fields",
        "clear_fields",
        "side_effects",
        "rollback",
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
_RECOGNIZED_TRIGGER_KEYS = frozenset({"type", "name"})

_KNOWN_ROUTE_KINDS = frozenset(
    {"forward", "return", "loop", "side", "revert", "terminal"}
)
_KNOWN_TRIGGER_TYPES = frozenset({"command", "event", "runtime_event", "condition"})


def workflow_path(project_dir: Path) -> Path:
    """Return ``<project_dir>/workflow.yaml`` (may not exist)."""
    return project_dir / WORKFLOW_FILENAME


def _audit_workflow_shape(wf_id: str, raw: dict) -> list[WorkflowFinding]:
    """Walk the raw workflow tree and emit ``workflow/unknown_key`` for
    every field the schema doesn't recognize at any level.

    Hard-migration policy: the loader is name-blind. It does not know
    what previous releases called any key — it only knows what the
    current schema accepts. Stale shapes therefore surface as a single
    error code with the offending key in the message, alongside the
    recognized-key list so the author can correct the file.
    """
    findings: list[WorkflowFinding] = []

    def _emit_unknown(
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
        _emit_unknown(
            set(raw.keys()) - _RECOGNIZED_WORKFLOW_KEYS,
            _RECOGNIZED_WORKFLOW_KEYS,
            f"workflow {wf_id!r}",
            status=None,
        )

        instance_raw = raw.get("instance")
        if isinstance(instance_raw, dict):
            unknown_instance = set(instance_raw.keys()) - _RECOGNIZED_INSTANCE_KEYS
            for key in sorted(unknown_instance):
                findings.append(
                    WorkflowFinding(
                        code="workflow/instance_unknown_field",
                        workflow=wf_id,
                        status=None,
                        message=(
                            f"unknown field {key!r} in `instance:` block on "
                            f"workflow {wf_id!r}; recognized fields are "
                            f"{sorted(_RECOGNIZED_INSTANCE_KEYS)}"
                        ),
                    )
                )

        for status_raw in raw.get("statuses") or []:
            if not isinstance(status_raw, dict):
                continue
            sid = str(status_raw.get("id") or "<unknown>")
            present = set(status_raw.keys())
            _emit_unknown(
                present - _RECOGNIZED_STATUS_KEYS,
                _RECOGNIZED_STATUS_KEYS,
                f"status {sid!r}",
                status=sid,
            )

            artifacts_raw = status_raw.get("artifacts")
            if isinstance(artifacts_raw, dict):
                _emit_unknown(
                    set(artifacts_raw.keys()) - _RECOGNIZED_ARTIFACTS_KEYS,
                    _RECOGNIZED_ARTIFACTS_KEYS,
                    f"status {sid!r} `artifacts:`",
                    status=sid,
                )
                for bucket in ("produces", "consumes"):
                    for ref in artifacts_raw.get(bucket) or []:
                        if isinstance(ref, dict):
                            _emit_unknown(
                                set(ref.keys()) - _RECOGNIZED_ARTIFACT_REF_KEYS,
                                _RECOGNIZED_ARTIFACT_REF_KEYS,
                                f"status {sid!r} `artifacts.{bucket}` entry",
                                status=sid,
                            )

            for step in status_raw.get("work_steps") or []:
                if isinstance(step, dict):
                    _emit_unknown(
                        set(step.keys()) - _RECOGNIZED_WORK_STEP_KEYS,
                        _RECOGNIZED_WORK_STEP_KEYS,
                        f"status {sid!r} work-step",
                        status=sid,
                    )

            for link in status_raw.get("cross_links") or []:
                if isinstance(link, dict):
                    _emit_unknown(
                        set(link.keys()) - _RECOGNIZED_CROSS_LINK_KEYS,
                        _RECOGNIZED_CROSS_LINK_KEYS,
                        f"status {sid!r} cross-link",
                        status=sid,
                    )

        for route_raw in raw.get("routes") or []:
            if not isinstance(route_raw, dict):
                continue
            rid = str(route_raw.get("id") or "<unknown>")
            _emit_unknown(
                set(route_raw.keys()) - _RECOGNIZED_ROUTE_KEYS,
                _RECOGNIZED_ROUTE_KEYS,
                f"route {rid!r}",
                status=None,
            )

            controls_raw = route_raw.get("controls")
            if isinstance(controls_raw, dict):
                _emit_unknown(
                    set(controls_raw.keys()) - _RECOGNIZED_CONTROLS_KEYS,
                    _RECOGNIZED_CONTROLS_KEYS,
                    f"route {rid!r} `controls:`",
                    status=None,
                )

            emits_raw = route_raw.get("emits")
            if isinstance(emits_raw, dict):
                _emit_unknown(
                    set(emits_raw.keys()) - _RECOGNIZED_EMITS_KEYS,
                    _RECOGNIZED_EMITS_KEYS,
                    f"route {rid!r} `emits:`",
                    status=None,
                )
                for ref in emits_raw.get("artifacts") or []:
                    if isinstance(ref, dict):
                        _emit_unknown(
                            set(ref.keys()) - _RECOGNIZED_ARTIFACT_REF_KEYS,
                            _RECOGNIZED_ARTIFACT_REF_KEYS,
                            f"route {rid!r} `emits.artifacts` entry",
                            status=None,
                        )

            trigger_raw = route_raw.get("trigger")
            if isinstance(trigger_raw, dict):
                _emit_unknown(
                    set(trigger_raw.keys()) - _RECOGNIZED_TRIGGER_KEYS,
                    _RECOGNIZED_TRIGGER_KEYS,
                    f"route {rid!r} `trigger:`",
                    status=None,
                )

    return findings


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

    load_findings: list[WorkflowFinding] = []

    # Top-level unknown-key audit (catches typos like `workflow_schema:`
    # or stale top-level shapes).
    unknown_top = set(raw.keys()) - _RECOGNIZED_TOPLEVEL_KEYS
    for key in sorted(unknown_top):
        load_findings.append(
            WorkflowFinding(
                code="workflow/unknown_key",
                workflow="<root>",
                status=None,
                message=(
                    f"unknown top-level key {key!r}; recognized keys are "
                    f"{sorted(_RECOGNIZED_TOPLEVEL_KEYS)}"
                ),
            )
        )

    schema_version_raw = raw.get("workflow_schema_version")
    # Accept both bare-int (`workflow_schema_version: 1`) and
    # quoted-string (`workflow_schema_version: "1"`) shapes — YAML
    # serializers can produce either depending on quoting.
    if isinstance(schema_version_raw, int):
        schema_version = schema_version_raw
    elif isinstance(schema_version_raw, str) and schema_version_raw.strip().isdigit():
        schema_version = int(schema_version_raw.strip())
    else:
        schema_version = 0

    workflows_block = raw.get("workflows") or {}
    if not isinstance(workflows_block, dict):
        return WorkflowSpec(schema_version=schema_version, load_findings=load_findings)

    workflows: dict[str, Workflow] = {}
    for wf_id, wf_raw in workflows_block.items():
        if not isinstance(wf_id, str):
            continue
        if not isinstance(wf_raw, dict):
            continue
        workflow, wf_findings = _parse_workflow(wf_id, wf_raw)
        workflows[wf_id] = workflow
        load_findings.extend(wf_findings)
    return WorkflowSpec(
        workflows=workflows,
        schema_version=schema_version,
        load_findings=load_findings,
    )


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
    instance = _parse_instance(raw.get("instance"))
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
                instance=instance,
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
                instance=instance,
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
            instance=instance,
        ),
        findings,
    )


def _parse_instance(value: Any) -> WorkflowInstanceShape | None:
    """Parse an ``instance:`` block into a :class:`WorkflowInstanceShape`.

    Returns ``None`` when the block is absent or shaped wrong; the
    workflow-level missing-block warning fires from
    :func:`validate_workflow_spec`.
    """
    if not isinstance(value, dict):
        return None
    storage_path = str(value.get("storage_path", "")).strip()
    status_field = str(value.get("status_field", "")).strip()
    if not storage_path or not status_field:
        return None
    return WorkflowInstanceShape(
        storage_path=storage_path,
        status_field=status_field,
        status_enum=_str_list(value.get("status_enum")),
        required_fields=_str_list(value.get("required_fields")),
        instance_id_field=str(value.get("instance_id_field") or "id").strip(),
        singleton=bool(value.get("singleton", False)),
        reference_only=bool(value.get("reference_only", False)),
    )


def _parse_status(
    wf_id: str, raw: dict
) -> tuple[WorkflowStatus, list[WorkflowFinding]]:
    sid = str(raw.get("id", "")) or "<unknown>"
    findings: list[WorkflowFinding] = []
    terminal = bool(raw.get("terminal", False))

    return (
        WorkflowStatus(
            id=sid,
            terminal=terminal,
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


def _parse_route_trigger(value: Any) -> tuple[str | None, WorkflowRouteTrigger | None]:
    """Return the bare-string form alongside an optional typed form.

    Accepts either:

    - bare string ``trigger: command.pm-session-spawn`` — preserved as-is
      in the bare-string slot; not coerced into typed form
    - mapping ``trigger: { type: command, name: ... }`` — produces a
      typed :class:`WorkflowRouteTrigger`; the bare-string slot
      receives ``"<type>.<name>"`` for round-trip rendering.
    """
    if value is None:
        return None, None
    if isinstance(value, str):
        bare = value.strip() or None
        return bare, None
    if isinstance(value, dict):
        type_raw = str(value.get("type") or "").strip()
        name_raw = str(value.get("name") or "").strip()
        if not type_raw or not name_raw:
            return None, None
        ttype = type_raw if type_raw in _KNOWN_TRIGGER_TYPES else "condition"
        bare = f"{ttype}.{name_raw}"
        return bare, WorkflowRouteTrigger(type=ttype, name=name_raw, raw=bare)  # type: ignore[arg-type]
    return None, None


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
        if kind not in _KNOWN_ROUTE_KINDS:
            kind = _classify_route_kind(from_ref, to_ref, status_index)
        label = str(entry.get("label") or entry.get("command") or route_id).strip()
        command = entry.get("command")
        rollback_raw = str(entry.get("rollback") or "atomic").strip()
        rollback = rollback_raw if rollback_raw in ("atomic", "none") else "atomic"
        bare_trigger, typed_trigger = _parse_route_trigger(entry.get("trigger"))
        routes.append(
            WorkflowRoute(
                id=route_id,
                actor=str(entry.get("actor", "")).strip(),
                from_ref=from_ref,
                to_ref=to_ref,
                kind=kind,  # type: ignore[arg-type]
                label=label,
                trigger=bare_trigger,
                trigger_typed=typed_trigger,
                command=str(command).strip() if command else None,
                controls=_parse_route_controls(entry.get("controls")),
                signals=_str_list(entry.get("signals")),
                skills=_str_list(entry.get("skills")),
                emits=_parse_route_emits(entry.get("emits")),
                preserve_fields=_str_list(entry.get("preserve_fields")),
                clear_fields=_str_list(entry.get("clear_fields")),
                side_effects=_str_list(entry.get("side_effects")),
                rollback=rollback,  # type: ignore[arg-type]
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
