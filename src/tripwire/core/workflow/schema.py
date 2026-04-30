"""Typed schema for ``workflow.yaml``.

The shape:

.. code-block:: yaml

    workflows:
      <workflow-id>:
        actor: <actor-name>
        trigger: <event-name>
        stations:
          - id: <station-id>
            next: <station-id>          # single
            # or
            next:                        # conditional
              - if: <predicate>
                then: <station-id>
              - else: <station-id>      # default branch
            # or
            terminal: true               # terminal station
            prompt_checks: [<id>, ...]
            validators: [<id>, ...]
            tripwires: [<id>, ...]

Conditional predicates are equality-only for v0.9 (locked decision in
``backlog-architecture.md``): ``<dot-path> (==|!=) <bare-value>``.

The schema lives here as plain dataclasses (not Pydantic) — the loader
parses the raw YAML into these structures so we control coercion and
error messages directly. Pydantic was considered but the file shape
involves three distinct ``next:`` shapes that are awkward to express
as a discriminated-union BaseModel; the dataclass tree keeps the
runtime contract readable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ----------------------------------------------------------------------
# Predicate — equality-only for v0.9
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Predicate:
    """Equality predicate of the form ``<dot-path> <op> <value>``.

    ``field`` is a dot-path into the workflow context (e.g.
    ``agent.role``). ``op`` is ``==`` or ``!=``. ``value`` is the
    right-hand bare token, treated as a string literal.

    Numerical thresholds and conjunctions are deliberately excluded —
    add operators only when a real workflow needs them. See
    ``backlog-architecture.md`` decision #2.
    """

    field: str
    op: Literal["==", "!="]
    value: str

    @classmethod
    def parse(cls, expr: str) -> Predicate:
        """Parse ``"<lhs> <op> <rhs>"`` into a :class:`Predicate`.

        Raises :class:`ValueError` if the operator is unsupported or
        the expression is malformed.
        """
        if "==" in expr:
            op: Literal["==", "!="] = "=="
            lhs, _, rhs = expr.partition("==")
        elif "!=" in expr:
            op = "!="
            lhs, _, rhs = expr.partition("!=")
        else:
            raise ValueError(
                f"predicate {expr!r} must contain `==` or `!=` "
                f"(equality-only per workflow.yaml v0.9 spec)"
            )
        lhs = lhs.strip()
        rhs = rhs.strip()
        if not lhs or not rhs:
            raise ValueError(
                f"predicate {expr!r} must have non-empty operands on both sides"
            )
        return cls(field=lhs, op=op, value=rhs)

    def evaluate(self, ctx: dict) -> bool:
        """Resolve ``self.field`` against ``ctx`` and apply ``self.op``.

        A missing field resolves to ``None``. ``None`` never equals a
        non-empty string literal, so a missing field on an ``==`` check
        is False.
        """
        cur: object = ctx
        for part in self.field.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        if self.op == "==":
            return cur == self.value
        return cur != self.value


# ----------------------------------------------------------------------
# Next-spec — single id | conditional branches | terminal
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ConditionalBranch:
    """One branch of a conditional ``next:`` list.

    ``predicate=None`` marks the default (``else``) branch.
    """

    predicate: Predicate | None
    then: str


@dataclass(frozen=True)
class NextSpec:
    """Discriminated union over the three ``next:`` shapes.

    ``kind`` is the discriminator. ``single`` is set when ``kind ==
    "single"``; ``conditional`` is set when ``kind == "conditional"``.
    Both stay ``None`` when the station is terminal.
    """

    kind: Literal["single", "conditional", "terminal"]
    single: str | None = None
    conditional: list[ConditionalBranch] | None = None


# ----------------------------------------------------------------------
# Station + workflow + spec
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Station:
    id: str
    next: NextSpec
    prompt_checks: list[str] = field(default_factory=list)
    validators: list[str] = field(default_factory=list)
    tripwires: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Workflow:
    id: str
    actor: str
    trigger: str
    stations: list[Station]

    @property
    def stations_by_id(self) -> dict[str, Station]:
        return {s.id: s for s in self.stations}


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
    station: str | None
    message: str
    severity: Literal["error", "warning"] = "error"


@dataclass(frozen=True)
class WorkflowSpec:
    """The parsed contents of ``workflow.yaml``.

    Empty (``workflows == {}``) when the file is missing or absent.

    ``load_findings`` carries any structural anomalies the loader
    detected before constructing the typed tree (e.g. a station that
    had both ``terminal: true`` and a ``next:`` key — a coherent
    :class:`NextSpec` can't represent that, so the loader records it
    as a finding and discards one side). :func:`validate_workflow_spec`
    surfaces these alongside its own checks.
    """

    workflows: dict[str, Workflow] = field(default_factory=dict)
    load_findings: list[WorkflowFinding] = field(default_factory=list)


# ----------------------------------------------------------------------
# Well-formedness validator
# ----------------------------------------------------------------------


def validate_workflow_spec(
    spec: WorkflowSpec,
    *,
    known_validators: set[str],
    known_tripwires: set[str],
    known_prompt_checks: set[str],
) -> list[WorkflowFinding]:
    """Run well-formedness checks against a parsed :class:`WorkflowSpec`.

    Returns a list of findings. The caller routes findings into the
    main validator report (or rejects the load entirely for fatal
    cases). Detected failure modes:

    - ``workflow/duplicate_station_id`` — two stations share an id
    - ``workflow/unknown_next_station`` — ``next:`` refers to a station
      id not declared in the same workflow
    - ``workflow/terminal_with_next`` — a station marks ``terminal: true``
      AND declares ``next``
    - ``workflow/no_terminal_station`` — the workflow has no terminal
      station (every workflow must converge)
    - ``workflow/unknown_validator`` / ``workflow/unknown_tripwire`` /
      ``workflow/unknown_prompt_check`` — a station references a
      validator / tripwire / prompt-check that isn't registered
    """
    findings: list[WorkflowFinding] = list(spec.load_findings)
    for wf_id, wf in spec.workflows.items():
        findings.extend(_check_workflow(wf_id, wf))
        findings.extend(
            _check_refs(
                wf_id,
                wf,
                known_validators=known_validators,
                known_tripwires=known_tripwires,
                known_prompt_checks=known_prompt_checks,
            )
        )
    return findings


def _check_workflow(wf_id: str, wf: Workflow) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    seen: set[str] = set()
    has_terminal = False
    for station in wf.stations:
        if station.id in seen:
            out.append(
                WorkflowFinding(
                    code="workflow/duplicate_station_id",
                    workflow=wf_id,
                    station=station.id,
                    message=f"station id {station.id!r} declared more than once",
                )
            )
        seen.add(station.id)
        if station.next.kind == "terminal":
            has_terminal = True
    if not has_terminal and wf.stations:
        out.append(
            WorkflowFinding(
                code="workflow/no_terminal_station",
                workflow=wf_id,
                station=None,
                message=(
                    f"workflow {wf_id!r} has no terminal station — every "
                    f"workflow must declare at least one station with "
                    f"`terminal: true`"
                ),
            )
        )
    out.extend(_check_next_refs(wf_id, wf, declared_ids=seen))
    return out


def _check_next_refs(
    wf_id: str, wf: Workflow, *, declared_ids: set[str]
) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    for station in wf.stations:
        nxt = station.next
        if nxt.kind == "single":
            assert nxt.single is not None
            if nxt.single not in declared_ids:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_next_station",
                        workflow=wf_id,
                        station=station.id,
                        message=(
                            f"station {station.id!r} `next:` references "
                            f"{nxt.single!r} which is not declared in "
                            f"workflow {wf_id!r}"
                        ),
                    )
                )
        elif nxt.kind == "conditional":
            assert nxt.conditional is not None
            for branch in nxt.conditional:
                if branch.then not in declared_ids:
                    out.append(
                        WorkflowFinding(
                            code="workflow/unknown_next_station",
                            workflow=wf_id,
                            station=station.id,
                            message=(
                                f"station {station.id!r} conditional branch "
                                f"`then: {branch.then!r}` is not declared "
                                f"in workflow {wf_id!r}"
                            ),
                        )
                    )
    return out


def _check_refs(
    wf_id: str,
    wf: Workflow,
    *,
    known_validators: set[str],
    known_tripwires: set[str],
    known_prompt_checks: set[str],
) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    for station in wf.stations:
        for ref in station.validators:
            if known_validators and ref not in known_validators:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_validator",
                        workflow=wf_id,
                        station=station.id,
                        message=(
                            f"station {station.id!r} references validator "
                            f"{ref!r} which is not registered"
                        ),
                    )
                )
        for ref in station.tripwires:
            if known_tripwires and ref not in known_tripwires:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_tripwire",
                        workflow=wf_id,
                        station=station.id,
                        message=(
                            f"station {station.id!r} references tripwire "
                            f"{ref!r} which is not registered"
                        ),
                    )
                )
        for ref in station.prompt_checks:
            if known_prompt_checks and ref not in known_prompt_checks:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_prompt_check",
                        workflow=wf_id,
                        station=station.id,
                        message=(
                            f"station {station.id!r} references prompt-check "
                            f"{ref!r} which is not registered"
                        ),
                    )
                )
    return out


__all__ = [
    "ConditionalBranch",
    "NextSpec",
    "Predicate",
    "Station",
    "Workflow",
    "WorkflowFinding",
    "WorkflowSpec",
    "validate_workflow_spec",
]
