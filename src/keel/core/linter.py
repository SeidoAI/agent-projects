"""Lint framework for heuristic, stage-aware checks.

Separate from the validator: validator is mechanical (schema/refs);
lint is heuristic (did someone actually do the work). Stages are:
- scoping  — during /pm-scope or /pm-rescope
- handoff  — before /pm-session-launch
- session  — in-flight session health check

Rules are registered via ``@register_rule`` and matched by stage at
run time. Exit codes: 0 (info-only), 1 (warning present), 2 (error
present).

Severity in registration is the rule's *default*; individual findings
can override via ``LintFinding.severity``. ``exit_code_for`` reads
the per-finding severity, so dynamic severities (e.g. info → warning
when workspace is linked) work transparently.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

LintStage = Literal["scoping", "handoff", "session"]
LintSeverity = Literal["info", "warning", "error"]


@dataclass
class LintFinding:
    code: str
    severity: LintSeverity
    message: str
    file: str
    fix_hint: str | None = None


@dataclass
class LintContext:
    project_dir: Path
    session_id: str | None = None  # for session-stage rules


@dataclass
class LintRule:
    code: str
    stage: LintStage
    severity: LintSeverity
    func: Callable[[LintContext], Iterable[LintFinding]]


_registry: list[LintRule] = []


def register_rule(*, stage: LintStage, code: str, severity: LintSeverity):
    """Decorator to register a lint rule.

    ``severity`` is the rule's default; per-finding severity takes
    precedence in ``exit_code_for`` and the CLI report.
    """

    def _wrap(func):
        _registry.append(LintRule(code=code, stage=stage, severity=severity, func=func))
        return func

    return _wrap


def registered_rules() -> list[LintRule]:
    """Return the full rule registry (read-only, for tests / introspection)."""
    return list(_registry)


class Linter:
    def __init__(self, project_dir: Path, session_id: str | None = None):
        self.ctx = LintContext(project_dir=project_dir, session_id=session_id)

    def run_stage(self, stage: LintStage) -> Iterable[LintFinding]:
        for rule in _registry:
            if rule.stage != stage:
                continue
            yield from rule.func(self.ctx)


def exit_code_for(findings: list[LintFinding]) -> int:
    """Map findings to an exit code: 0 (info-only), 1 (warning), 2 (error)."""
    if any(f.severity == "error" for f in findings):
        return 2
    if any(f.severity == "warning" for f in findings):
        return 1
    return 0
