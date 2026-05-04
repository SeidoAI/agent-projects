"""Typed schema for ``workflow.yaml``.

The shape:

.. code-block:: yaml

    workflows:
      <workflow-id>:
        actor: <actor-name>
        trigger: <event-name>
        statuses:
          - id: <status-id>
            next: <status-id>          # single
            # or
            next:                        # conditional
              - if: <predicate>
                then: <status-id>
              - else: <status-id>      # default branch
            # or
            terminal: true               # terminal status
            prompt_checks: [<id>, ...]
            validators: [<id>, ...]
            jit_prompts: [<id>, ...]
            artifacts:
              produces:
                - id: <artifact-id>
                  label: <display-label>
                  path: <optional-path-template>
              consumes:
                - id: <artifact-id>
                  label: <display-label>

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
    Both stay ``None`` when the status is terminal.
    """

    kind: Literal["single", "conditional", "terminal"]
    single: str | None = None
    conditional: list[ConditionalBranch] | None = None


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
class WorkflowStatus:
    id: str
    next: NextSpec
    prompt_checks: list[str] = field(default_factory=list)
    validators: list[str] = field(default_factory=list)
    jit_prompts: list[str] = field(default_factory=list)
    artifacts: WorkflowStatusArtifacts = field(default_factory=WorkflowStatusArtifacts)


@dataclass(frozen=True)
class Workflow:
    id: str
    actor: str
    trigger: str
    statuses: list[WorkflowStatus]

    @property
    def statuses_by_id(self) -> dict[str, WorkflowStatus]:
        return {s.id: s for s in self.statuses}


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
    """The parsed contents of ``workflow.yaml``.

    Empty (``workflows == {}``) when the file is missing or absent.

    ``load_findings`` carries any structural anomalies the loader
    detected before constructing the typed tree (e.g. a status that
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
    known_jit_prompts: set[str],
    known_prompt_checks: set[str],
) -> list[WorkflowFinding]:
    """Run well-formedness checks against a parsed :class:`WorkflowSpec`.

    Returns a list of findings. The caller routes findings into the
    main validator report (or rejects the load entirely for fatal
    cases). Detected failure modes:

    - ``workflow/duplicate_status_id`` — two statuses share an id
    - ``workflow/unknown_next_status`` — ``next:`` refers to a status
      id not declared in the same workflow
    - ``workflow/terminal_with_next`` — a status marks ``terminal: true``
      AND declares ``next``
    - ``workflow/no_terminal_status`` — the workflow has no terminal
      status (every workflow must converge)
    - ``workflow/unknown_validator`` / ``workflow/unknown_jit_prompt`` /
      ``workflow/unknown_prompt_check`` — a status references a
      validator / JIT prompt / prompt-check implementation that does
      not exist
    """
    findings: list[WorkflowFinding] = list(spec.load_findings)
    for wf_id, wf in spec.workflows.items():
        findings.extend(_check_workflow(wf_id, wf))
        findings.extend(
            _check_refs(
                wf_id,
                wf,
                known_validators=known_validators,
                known_jit_prompts=known_jit_prompts,
                known_prompt_checks=known_prompt_checks,
            )
        )
    return findings


def _check_workflow(wf_id: str, wf: Workflow) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    seen: set[str] = set()
    has_terminal = False
    for status in wf.statuses:
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
        if status.next.kind == "terminal":
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
    out.extend(_check_next_refs(wf_id, wf, declared_ids=seen))
    return out


def _check_next_refs(
    wf_id: str, wf: Workflow, *, declared_ids: set[str]
) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    for status in wf.statuses:
        nxt = status.next
        if nxt.kind == "single":
            assert nxt.single is not None
            if nxt.single not in declared_ids:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_next_status",
                        workflow=wf_id,
                        status=status.id,
                        message=(
                            f"status {status.id!r} `next:` references "
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
                            code="workflow/unknown_next_status",
                            workflow=wf_id,
                            status=status.id,
                            message=(
                                f"status {status.id!r} conditional branch "
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
    known_jit_prompts: set[str],
    known_prompt_checks: set[str],
) -> list[WorkflowFinding]:
    out: list[WorkflowFinding] = []
    for status in wf.statuses:
        for ref in status.validators:
            if known_validators and ref not in known_validators:
                out.append(
                    WorkflowFinding(
                        code="workflow/unknown_validator",
                        workflow=wf_id,
                        status=status.id,
                        message=(
                            f"status {status.id!r} references validator "
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
    return out


__all__ = [
    "ConditionalBranch",
    "NextSpec",
    "Predicate",
    "Workflow",
    "WorkflowArtifactRef",
    "WorkflowFinding",
    "WorkflowSpec",
    "WorkflowStatus",
    "WorkflowStatusArtifacts",
    "validate_workflow_spec",
]
