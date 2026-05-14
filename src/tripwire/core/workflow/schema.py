"""Typed schema for ``workflow.yaml`` (v0.13).

The shape:

.. code-block:: yaml

    workflow_schema_version: 1
    workflows:
      <workflow-id>:
        actor: <actor-name>
        trigger: <event-name>
        statuses:
          - id: <status-id>
            terminal: true | false       # default false
            prompt_checks: [<id>, ...]
            tripwires: [<id>, ...]       # hard pass/fail gates
            heuristics: [<id>, ...]      # soft warn-once checks
            jit_prompts: [<id>, ...]     # hidden + ack
            artifacts:
              produces: [...]
              consumes: [...]
        routes:
          - id: <route-id>
            actor: pm-agent | coding-agent | code
            from: <status-id> | source:<name>
            to: <status-id> | sink:<name>
            kind: forward | return | loop | side | revert | terminal
            command: <optional-command-id>
            trigger: <optional-event-or-condition>
            preserve_fields: [<dot-path>, ...]      # survive transition
            clear_fields: [<dot-path>, ...]         # cleared on transition
            side_effects: [<registered-id>, ...]    # ordered apply
            rollback: atomic | none                 # default atomic
            controls:
              tripwires: [<id>, ...]
              heuristics: [<id>, ...]
              prompt_checks: [<id>, ...]
              jit_prompts: [<id>, ...]
            skills: [<skill-id>, ...]
            emits:
              artifacts: [...]
              events: [...]
              status_changes: [...]

Four-primitive control model (locked):

- ``tripwire`` — hard pass/fail gate; blocks until file/state passes
- ``heuristic`` — soft warn-once detector; does not block
- ``jit_prompt`` — hidden ack-required prompt
- ``prompt_check`` — required slash-command invocation

Routes are the SINGLE source of structural arrows; ``statuses[].next:``
is removed in v0.13. Terminal-ness is an explicit boolean on the status.

The schema lives here as plain dataclasses (not Pydantic) — the loader
parses raw YAML into these structures so we control coercion and
error messages directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

KNOWN_ROUTE_ACTORS = frozenset({"pm-agent", "coding-agent", "code"})
ROUTE_KINDS = frozenset({"forward", "return", "loop", "side", "revert", "terminal"})
ROLLBACK_MODES = frozenset({"atomic", "none"})

WORKFLOW_SCHEMA_VERSION = 1


# ----------------------------------------------------------------------
# Status + workflow + spec
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class WorkflowArtifactRef:
    """One workflow-declared proof object.

    ``path`` is optional in v0.9.6. It lets a future UI deep-link to
    expected files without making live session files the source of truth
    for the process definition.
    """

    id: str
    label: str
    path: str | None = None


@dataclass(frozen=True)
class WorkflowStatusArtifacts:
    produces: list[WorkflowArtifactRef] = field(default_factory=list)
    consumes: list[WorkflowArtifactRef] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowInstanceShape:
    """Declared instance shape for a workflow (v0.13.1).

    Each workflow's runtime instances (sessions, issues, scoping runs,
    etc.) live somewhere on disk and carry a status field. This block
    declares that contract so ``tripwire validate`` can enforce it
    uniformly across every workflow.

    ``storage_path`` is the disk layout for an instance file. It is a
    string template with ``{instance_id}`` substituted at runtime; in
    v0.13 the path uses the current flat layout (e.g.
    ``sessions/{instance_id}/session.yaml``). Step 7a rewrites these
    to ``instances/<type>/``.

    ``status_field`` is the dot-path of the status field on the
    instance model. ``status_enum`` enumerates the legal values.
    ``required_fields`` lists the always-present fields a well-formed
    instance must carry (sanity check, not exhaustive). ``instance_id_field``
    names the field that holds the id used to render ``storage_path``;
    almost always ``id``.

    The block is optional in v0.13.1 — a missing block surfaces a
    ``workflow/instance_missing`` warning but doesn't fail load. It
    becomes mandatory in v0.14.
    """

    storage_path: str
    status_field: str
    status_enum: list[str]
    required_fields: list[str] = field(default_factory=list)
    instance_id_field: str = "id"


@dataclass(frozen=True)
class WorkflowWorkStep:
    """Work performed by an actor *inside* a status — no status change.

    Routes (transitions) move between statuses; work_steps describe the
    actor's labour while they are in the status. The canonical example
    is `implement` inside `executing`: the coding agent loads its
    SKILL.md files, reads the plan, and produces the diff. None of
    that is a route — it's the work *between* the route that put the
    session into `executing` and the route that advances it to
    `in_review`.
    """

    id: str
    actor: str
    label: str
    skills: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowCrossLink:
    """A link from this status to a status in another workflow.

    ``kind`` is ``"triggers"`` when this status hands off to the target
    workflow (the canonical write side), or ``"triggered_by"`` for the
    inverse documentation. The renderer always draws the edge using the
    ``triggers`` side; ``triggered_by`` entries are advisory.

    ``pm_subagent_dispatch`` flags that the dispatched workflow should
    run inside a Claude Code subagent (Task-style spawn) rather than
    the parent PM agent's session — used by the pm-monitor overseer
    loop when fanning out work.
    """

    workflow: str
    status: str
    label: str | None = None
    kind: Literal["triggers", "triggered_by"] = "triggers"
    pm_subagent_dispatch: bool = False


@dataclass(frozen=True)
class WorkflowStatus:
    """A node in the lifecycle.

    ``terminal`` is the explicit terminal-ness flag — terminal statuses
    must have no outbound routes (other than to boundary ports).
    """

    id: str
    terminal: bool = False
    prompt_checks: list[str] = field(default_factory=list)
    tripwires: list[str] = field(default_factory=list)
    heuristics: list[str] = field(default_factory=list)
    jit_prompts: list[str] = field(default_factory=list)
    artifacts: WorkflowStatusArtifacts = field(default_factory=WorkflowStatusArtifacts)
    work_steps: list[WorkflowWorkStep] = field(default_factory=list)
    cross_links: list[WorkflowCrossLink] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowRouteControls:
    tripwires: list[str] = field(default_factory=list)
    heuristics: list[str] = field(default_factory=list)
    jit_prompts: list[str] = field(default_factory=list)
    prompt_checks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowRouteEmits:
    artifacts: list[WorkflowArtifactRef] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    status_changes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowRouteTrigger:
    """Typed trigger for a route (v0.13).

    ``type`` is one of ``command``, ``event``, ``runtime_event``, or
    ``condition``. ``name`` is the typed handle (e.g. command id or
    event name). ``raw`` preserves the original string for diagnostic
    rendering; if the YAML provided a bare string we record it both
    in ``raw`` and as ``type='condition'``.
    """

    type: Literal["command", "event", "runtime_event", "condition"]
    name: str
    raw: str | None = None


@dataclass(frozen=True)
class WorkflowRoute:
    """One routed process segment in a workflow map.

    ``from_ref`` and ``to_ref`` are status ids or boundary ports such as
    ``source:issue`` and ``sink:merged``. The API serializes them back to
    ``from`` and ``to`` so ``workflow.yaml`` remains readable.

    ``signals`` lists the pm-monitor signal predicates that fire this
    route (e.g. ``signal.session_unblocked``). Used by the overseer
    loop to wire dispatch routes back to their source signals.

    ``preserve_fields`` / ``clear_fields`` / ``side_effects`` /
    ``rollback`` are the v0.13 executor contract: the dispatcher reads
    them to drive the transition.
    """

    id: str
    actor: str
    from_ref: str
    to_ref: str
    kind: Literal["forward", "return", "loop", "side", "revert", "terminal"]
    label: str
    trigger: str | None = None
    trigger_typed: WorkflowRouteTrigger | None = None
    command: str | None = None
    controls: WorkflowRouteControls = field(default_factory=WorkflowRouteControls)
    signals: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    emits: WorkflowRouteEmits = field(default_factory=WorkflowRouteEmits)
    preserve_fields: list[str] = field(default_factory=list)
    clear_fields: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    rollback: Literal["atomic", "none"] = "atomic"


@dataclass(frozen=True)
class Workflow:
    id: str
    actor: str
    trigger: str
    statuses: list[WorkflowStatus]
    routes: list[WorkflowRoute] = field(default_factory=list)
    brief_description: str | None = None
    instance: WorkflowInstanceShape | None = None

    @property
    def statuses_by_id(self) -> dict[str, WorkflowStatus]:
        return {s.id: s for s in self.statuses}

    @property
    def routes_by_id(self) -> dict[str, WorkflowRoute]:
        return {r.id: r for r in self.routes}


@dataclass(frozen=True)
class WorkflowFinding:
    """A well-formedness violation in a parsed :class:`WorkflowSpec`.

    Mirrors :class:`tripwire.core.validator._types.CheckResult` enough
    to round-trip into the validator's report without a hard dependency
    on the validator package — keeps the workflow module importable
    by lower layers (event log, gate runner) without circular imports.
    """

    code: str
    workflow: str
    status: str | None
    message: str
    severity: Literal["error", "warning"] = "error"


@dataclass(frozen=True)
class WorkflowSpec:
    """The parsed contents of ``workflow.yaml`` (v0.13).

    Empty (``workflows == {}``) when the file is missing or absent.

    ``schema_version`` is the declared ``workflow_schema_version`` at
    the top of the file. ``0`` means absent or non-integer; the loader
    surfaces this as a ``workflow/missing_schema_version`` finding.

    ``load_findings`` carries any structural anomalies the loader
    detected before constructing the typed tree. :func:`validate_workflow_spec`
    surfaces these alongside its own checks.
    """

    workflows: dict[str, Workflow] = field(default_factory=dict)
    schema_version: int = 0
    load_findings: list[WorkflowFinding] = field(default_factory=list)


# ----------------------------------------------------------------------
# Well-formedness validator
# ----------------------------------------------------------------------


def validate_workflow_spec(
    spec: WorkflowSpec,
    *,
    known_tripwires: set[str],
    known_heuristics: set[str],
    known_jit_prompts: set[str],
    known_prompt_checks: set[str],
    known_commands: set[str] | None = None,
    known_skills: set[str] | None = None,
    known_side_effects: set[str] | None = None,
    known_status_field_paths: set[str] | None = None,
) -> list[WorkflowFinding]:
    """Run well-formedness checks against a parsed :class:`WorkflowSpec`.

    Returns a list of findings. The caller routes findings into the
    main validator report (or rejects the load entirely for fatal
    cases).

    ``known_side_effects`` is the set of registered side-effect handler
    ids; if ``None``, the ``unknown_side_effect`` lint is a no-op (used
    during WS1 before the registry exists).

    ``known_status_field_paths`` is the set of valid dot-paths on the
    ``AgentSession`` model; if ``None``, the ``unknown_status_field``
    lint is a no-op.
    """
    findings: list[WorkflowFinding] = list(spec.load_findings)
    findings.extend(_check_schema_version(spec))
    for wf_id, wf in spec.workflows.items():
        findings.extend(_check_workflow(wf_id, wf))
        findings.extend(
            _check_refs(
                wf_id,
                wf,
                known_tripwires=known_tripwires,
                known_heuristics=known_heuristics,
                known_jit_prompts=known_jit_prompts,
                known_prompt_checks=known_prompt_checks,
                known_commands=known_commands,
                known_skills=known_skills,
                known_side_effects=known_side_effects,
                known_status_field_paths=known_status_field_paths,
            )
        )
        findings.extend(_check_route_kinds(wf_id, wf))
        findings.extend(_check_reachability(wf_id, wf))
        findings.extend(_check_trap_statuses(wf_id, wf))
        findings.extend(_check_recovery_paths(wf_id, wf))
        findings.extend(_check_lossy_reverts(wf_id, wf))
    findings.extend(_check_cross_links(spec))
    return findings


def _check_schema_version(spec: WorkflowSpec) -> list[WorkflowFinding]:
    if not spec.workflows:
        # Empty spec: no file or empty file — schema_version finding
        # would be noisy.
        return []
    if spec.schema_version == WORKFLOW_SCHEMA_VERSION:
        return []
    if spec.schema_version == 0:
        return [
            WorkflowFinding(
                code="workflow/missing_schema_version",
                workflow="<root>",
                status=None,
                message=(
                    "workflow.yaml is missing top-level "
                    f"`workflow_schema_version: {WORKFLOW_SCHEMA_VERSION}`."
                ),
            )
        ]
    return [
        WorkflowFinding(
            code="workflow/missing_schema_version",
            workflow="<root>",
            status=None,
            message=(
                f"workflow.yaml declares `workflow_schema_version: "
                f"{spec.schema_version}` but this build only understands "
                f"version {WORKFLOW_SCHEMA_VERSION}. Upgrade tripwire or "
                f"update workflow.yaml to match."
            ),
        )
    ]


def _check_cross_links(spec: WorkflowSpec) -> list[WorkflowFinding]:
    """Warn when a status's `cross_links:` points at a workflow or status
    that doesn't exist. Cross-links are pure documentation (no runtime
    side-effect), so the finding is a warning rather than a hard error —
    the workflow still loads.
    """
    out: list[WorkflowFinding] = []
    statuses_by_wf: dict[str, set[str]] = {
        wf_id: {s.id for s in wf.statuses} for wf_id, wf in spec.workflows.items()
    }
    for wf_id, wf in spec.workflows.items():
        for status in wf.statuses:
            for link in status.cross_links:
                if link.workflow not in statuses_by_wf:
                    out.append(
                        WorkflowFinding(
                            code="workflow/cross_link_unknown_workflow",
                            workflow=wf_id,
                            status=status.id,
                            severity="warning",
                            message=(
                                f"status {status.id!r} cross_link points at "
                                f"workflow {link.workflow!r} which is not "
                                f"declared"
                            ),
                        )
                    )
                    continue
                if link.status not in statuses_by_wf[link.workflow]:
                    out.append(
                        WorkflowFinding(
                            code="workflow/cross_link_unknown_status",
                            workflow=wf_id,
                            status=status.id,
                            severity="warning",
                            message=(
                                f"status {status.id!r} cross_link points at "
                                f"{link.workflow}.{link.status!r} but that "
                                f"status is not declared in workflow "
                                f"{link.workflow!r}"
                            ),
                        )
                    )
    return out


def _check_workflow(wf_id: str, wf: Workflow) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    # v0.13.1: workflows should declare an `instance:` block describing
    # the runtime instance shape (storage path, status field, status
    # enum). Missing is a warning in v0.13.1 for back-compat; mandatory
    # in v0.14.
    if wf.instance is None:
        out.append(
            WorkflowFinding(
                code="workflow/instance_missing",
                workflow=wf_id,
                status=None,
                severity="warning",
                message=(
                    f"workflow {wf_id!r} declares no `instance:` block — "
                    f"add storage_path, status_field, status_enum so "
                    f"`tripwire validate` can enforce instance shape "
                    f"(warning in v0.13.1, mandatory in v0.14)"
                ),
            )
        )
    seen: set[str] = set()
    has_terminal = False
    for status in wf.statuses:
        # Surface duplicate skill loads across work_steps in the same
        # status. Multiple steps loading the same skill is legal at
        # runtime (the skill is loaded once, used by both) but the
        # declaration carries no information beyond the second mention
        # — a warning prods the author to drop the redundant entry.
        ws_skill_seen: dict[str, str] = {}
        for ws in status.work_steps:
            for sk in ws.skills:
                if sk in ws_skill_seen:
                    out.append(
                        WorkflowFinding(
                            code="workflow/duplicate_skill_in_status",
                            workflow=wf_id,
                            status=status.id,
                            severity="warning",
                            message=(
                                f"skill {sk!r} declared by both work_step "
                                f"{ws_skill_seen[sk]!r} and {ws.id!r} in "
                                f"status {status.id!r} — second declaration "
                                f"is redundant (skills load once per region)"
                            ),
                        )
                    )
                else:
                    ws_skill_seen[sk] = ws.id
        if status.id in seen:
            out.append(
                WorkflowFinding(
                    code="workflow/duplicate_status_id",
                    workflow=wf_id,
                    status=status.id,
                    message=f"status id {status.id!r} declared more than once",
                )
            )
        seen.add(status.id)
        if status.terminal:
            has_terminal = True
    if not has_terminal and wf.statuses:
        out.append(
            WorkflowFinding(
                code="workflow/no_terminal_status",
                workflow=wf_id,
                status=None,
                message=(
                    f"workflow {wf_id!r} has no terminal status — every "
                    f"workflow must declare at least one status with "
                    f"`terminal: true`"
                ),
            )
        )
    return out


def _check_route_kinds(wf_id: str, wf: Workflow) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    for route in wf.routes:
        if route.kind not in ROUTE_KINDS:
            out.append(
                WorkflowFinding(
                    code="workflow/unknown_route_kind",
                    workflow=wf_id,
                    status=None,
                    message=(
                        f"route {route.id!r} kind {route.kind!r} is not in "
                        f"{sorted(ROUTE_KINDS)}"
                    ),
                )
            )
        if route.rollback not in ROLLBACK_MODES:
            out.append(
                WorkflowFinding(
                    code="workflow/unknown_rollback_mode",
                    workflow=wf_id,
                    status=None,
                    message=(
                        f"route {route.id!r} rollback {route.rollback!r} is "
                        f"not in {sorted(ROLLBACK_MODES)}"
                    ),
                )
            )
    return out


def _check_reachability(wf_id: str, wf: Workflow) -> list[WorkflowFinding]:
    """Every non-source-port status must be reachable from at least one
    inbound route originating outside itself or from a boundary source.
    """
    out: list[WorkflowFinding] = []
    if not wf.statuses:
        return out
    declared = {s.id for s in wf.statuses}
    has_inbound: dict[str, bool] = dict.fromkeys(declared, False)
    # An inbound route counts unless it's a self-loop on the same status
    # (which would never let an external session enter the status fresh).
    # Source-port origins (`from: source:foo`) and any cross-status route
    # are valid entry points.
    for route in wf.routes:
        if route.to_ref in declared and route.from_ref != route.to_ref:
            has_inbound[route.to_ref] = True
    initial = wf.statuses[0].id
    has_inbound[initial] = True  # the canonical entry point
    for sid, reached in has_inbound.items():
        if not reached:
            out.append(
                WorkflowFinding(
                    code="workflow/unreachable_status",
                    workflow=wf_id,
                    status=sid,
                    message=(
                        f"status {sid!r} has no inbound route from another "
                        f"status or a source: port — it cannot be entered"
                    ),
                )
            )
    return out


def _check_trap_statuses(wf_id: str, wf: Workflow) -> list[WorkflowFinding]:
    """Every non-terminal status must have at least one outbound route.

    A terminal status with outbound routes is also surfaced (it's
    semantically inconsistent — terminal statuses are sinks).
    """
    out: list[WorkflowFinding] = []
    declared = {s.id for s in wf.statuses}
    # Track outbound routes by kind. Revert-kind exits from a terminal
    # status are the documented v0.13 reopen pattern (completed → paused)
    # — they do not violate terminal-ness.
    has_outbound: dict[str, bool] = dict.fromkeys(declared, False)
    has_non_revert_outbound: dict[str, bool] = dict.fromkeys(declared, False)
    for route in wf.routes:
        if route.from_ref in declared:
            has_outbound[route.from_ref] = True
            if route.kind != "revert":
                has_non_revert_outbound[route.from_ref] = True
    for status in wf.statuses:
        if status.terminal:
            if has_non_revert_outbound[status.id]:
                out.append(
                    WorkflowFinding(
                        code="workflow/terminal_with_outbound_route",
                        workflow=wf_id,
                        status=status.id,
                        message=(
                            f"status {status.id!r} declares `terminal: true` "
                            f"but has non-revert outbound routes — terminal "
                            f"statuses are sinks (revert-kind reopen edges "
                            f"are allowed)"
                        ),
                    )
                )
        elif not has_outbound[status.id]:
            out.append(
                WorkflowFinding(
                    code="workflow/trap_status",
                    workflow=wf_id,
                    status=status.id,
                    message=(
                        f"status {status.id!r} is non-terminal but has no "
                        f"outbound route — sessions entering this status "
                        f"have no way out"
                    ),
                )
            )
    return out


_OFF_PATH_STATUS_NAMES = frozenset({"paused", "failed"})


def _check_recovery_paths(wf_id: str, wf: Workflow) -> list[WorkflowFinding]:
    """An off-path non-terminal status (paused, failed) must have at
    least one route back to an on-path status. Off-path statuses that
    can only escape into ``abandoned`` produce dead ends like Gap C/D
    in PM handoff #5.
    """
    out: list[WorkflowFinding] = []
    on_path: set[str] = set()
    for status in wf.statuses:
        if status.id in _OFF_PATH_STATUS_NAMES:
            continue
        if status.id == "abandoned":
            continue
        on_path.add(status.id)
    for status in wf.statuses:
        if status.id not in _OFF_PATH_STATUS_NAMES:
            continue
        if status.terminal:
            continue
        recovery_exists = any(
            r.from_ref == status.id and r.to_ref in on_path for r in wf.routes
        )
        if not recovery_exists:
            out.append(
                WorkflowFinding(
                    code="workflow/no_recovery_path",
                    workflow=wf_id,
                    status=status.id,
                    message=(
                        f"off-path status {status.id!r} has no route back to "
                        f"an on-path status — recovery hints in error "
                        f"messages would lead to dead ends"
                    ),
                )
            )
    return out


def _check_lossy_reverts(wf_id: str, wf: Workflow) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    for route in wf.routes:
        if route.kind != "revert":
            continue
        if not route.preserve_fields:
            out.append(
                WorkflowFinding(
                    code="workflow/lossy_revert",
                    workflow=wf_id,
                    status=None,
                    severity="warning",
                    message=(
                        f"revert route {route.id!r} declares no "
                        f"`preserve_fields:` — the transition will lose all "
                        f"runtime state on rollback (e.g. claude_session_id)"
                    ),
                )
            )
    return out


def _check_refs(
    wf_id: str,
    wf: Workflow,
    *,
    known_tripwires: set[str],
    known_heuristics: set[str],
    known_jit_prompts: set[str],
    known_prompt_checks: set[str],
    known_commands: set[str] | None,
    known_skills: set[str] | None,
    known_side_effects: set[str] | None,
    known_status_field_paths: set[str] | None,
) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    for status in wf.statuses:
        for ref in status.tripwires:
            if known_tripwires and ref not in known_tripwires:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_tripwire",
                        workflow=wf_id,
                        status=status.id,
                        message=(
                            f"status {status.id!r} references tripwire "
                            f"{ref!r} which is not implemented"
                        ),
                    )
                )
        for ref in status.heuristics:
            if known_heuristics and ref not in known_heuristics:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_heuristic",
                        workflow=wf_id,
                        status=status.id,
                        message=(
                            f"status {status.id!r} references heuristic "
                            f"{ref!r} which is not implemented"
                        ),
                    )
                )
        for ref in status.jit_prompts:
            if known_jit_prompts and ref not in known_jit_prompts:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_jit_prompt",
                        workflow=wf_id,
                        status=status.id,
                        message=(
                            f"status {status.id!r} references JIT prompt "
                            f"{ref!r} which is not implemented"
                        ),
                    )
                )
        for ref in status.prompt_checks:
            if known_prompt_checks and ref not in known_prompt_checks:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_prompt_check",
                        workflow=wf_id,
                        status=status.id,
                        message=(
                            f"status {status.id!r} references prompt-check "
                            f"{ref!r} which is not implemented"
                        ),
                    )
                )
    out.extend(
        _check_route_refs(
            wf_id,
            wf,
            known_tripwires=known_tripwires,
            known_heuristics=known_heuristics,
            known_jit_prompts=known_jit_prompts,
            known_prompt_checks=known_prompt_checks,
            known_commands=known_commands,
            known_skills=known_skills,
            known_side_effects=known_side_effects,
            known_status_field_paths=known_status_field_paths,
        )
    )
    return out


def _check_route_refs(
    wf_id: str,
    wf: Workflow,
    *,
    known_tripwires: set[str],
    known_heuristics: set[str],
    known_jit_prompts: set[str],
    known_prompt_checks: set[str],
    known_commands: set[str] | None,
    known_skills: set[str] | None,
    known_side_effects: set[str] | None,
    known_status_field_paths: set[str] | None,
) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    declared_statuses = set(wf.statuses_by_id)
    seen_routes: set[str] = set()
    for route in wf.routes:
        status = _finding_status_for_route(route, declared_statuses)
        if route.id in seen_routes:
            out.append(
                WorkflowFinding(
                    code="workflow/duplicate_route_id",
                    workflow=wf_id,
                    status=status,
                    message=f"route id {route.id!r} declared more than once",
                )
            )
        seen_routes.add(route.id)
        if route.actor not in KNOWN_ROUTE_ACTORS:
            out.append(
                WorkflowFinding(
                    code="workflow/unknown_actor",
                    workflow=wf_id,
                    status=status,
                    message=(
                        f"route {route.id!r} actor {route.actor!r} is not one of "
                        f"{sorted(KNOWN_ROUTE_ACTORS)}"
                    ),
                )
            )
        for label, ref in (("from", route.from_ref), ("to", route.to_ref)):
            if not ref:
                out.append(
                    WorkflowFinding(
                        code="workflow/missing_route_endpoint",
                        workflow=wf_id,
                        status=status,
                        message=f"route {route.id!r} has no `{label}:` endpoint",
                    )
                )
            elif not _is_boundary_ref(ref) and ref not in declared_statuses:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_route_status",
                        workflow=wf_id,
                        status=status,
                        message=(
                            f"route {route.id!r} `{label}: {ref}` does not name a "
                            f"declared status or boundary port"
                        ),
                    )
                )
        if (
            known_commands is not None
            and route.command
            and route.command not in known_commands
        ):
            out.append(
                WorkflowFinding(
                    code="workflow/unknown_command",
                    workflow=wf_id,
                    status=status,
                    message=(
                        f"route {route.id!r} references command {route.command!r} "
                        f"which is not implemented"
                    ),
                )
            )
        for skill in route.skills:
            if known_skills is not None and skill not in known_skills:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_skill",
                        workflow=wf_id,
                        status=status,
                        message=(
                            f"route {route.id!r} references skill {skill!r} "
                            f"which is not implemented"
                        ),
                    )
                )
        for ref in route.controls.tripwires:
            if known_tripwires and ref not in known_tripwires:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_tripwire",
                        workflow=wf_id,
                        status=status,
                        message=(
                            f"route {route.id!r} references tripwire {ref!r} "
                            f"which is not implemented"
                        ),
                    )
                )
        for ref in route.controls.heuristics:
            if known_heuristics and ref not in known_heuristics:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_heuristic",
                        workflow=wf_id,
                        status=status,
                        message=(
                            f"route {route.id!r} references heuristic {ref!r} "
                            f"which is not implemented"
                        ),
                    )
                )
        for ref in route.controls.jit_prompts:
            if known_jit_prompts and ref not in known_jit_prompts:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_jit_prompt",
                        workflow=wf_id,
                        status=status,
                        message=(
                            f"route {route.id!r} references JIT prompt {ref!r} "
                            f"which is not implemented"
                        ),
                    )
                )
        for ref in route.controls.prompt_checks:
            if known_prompt_checks and ref not in known_prompt_checks:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_prompt_check",
                        workflow=wf_id,
                        status=status,
                        message=(
                            f"route {route.id!r} references prompt-check {ref!r} "
                            f"which is not implemented"
                        ),
                    )
                )
        for ref in route.side_effects:
            if known_side_effects is not None and ref not in known_side_effects:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_side_effect",
                        workflow=wf_id,
                        status=status,
                        message=(
                            f"route {route.id!r} references side-effect "
                            f"{ref!r} which is not registered"
                        ),
                    )
                )
        for path in (*route.preserve_fields, *route.clear_fields):
            if known_status_field_paths is not None and not _path_is_known(
                path, known_status_field_paths
            ):
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_status_field",
                        workflow=wf_id,
                        status=status,
                        message=(
                            f"route {route.id!r} preserve/clear path {path!r} "
                            f"is not a recognized AgentSession field"
                        ),
                    )
                )
    return out


def _path_is_known(path: str, known: set[str]) -> bool:
    """Return True iff ``path`` (a dot-path) is a prefix-match against
    any registered field path. Allows both ``runtime_state`` and
    ``runtime_state.claude_session_id`` to validate."""
    if path in known:
        return True
    head = path.split(".", 1)[0]
    return head in known


def _finding_status_for_route(route: WorkflowRoute, statuses: set[str]) -> str | None:
    if route.to_ref in statuses:
        return route.to_ref
    if route.from_ref in statuses:
        return route.from_ref
    return None


def _is_boundary_ref(ref: str) -> bool:
    return ref.startswith("source:") or ref.startswith("sink:")


__all__ = [
    "KNOWN_ROUTE_ACTORS",
    "ROLLBACK_MODES",
    "ROUTE_KINDS",
    "WORKFLOW_SCHEMA_VERSION",
    "Workflow",
    "WorkflowArtifactRef",
    "WorkflowCrossLink",
    "WorkflowFinding",
    "WorkflowInstanceShape",
    "WorkflowRoute",
    "WorkflowRouteControls",
    "WorkflowRouteEmits",
    "WorkflowRouteTrigger",
    "WorkflowSpec",
    "WorkflowStatus",
    "WorkflowStatusArtifacts",
    "WorkflowWorkStep",
    "validate_workflow_spec",
]
