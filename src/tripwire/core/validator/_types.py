"""Result + context types shared by every validator check.

Lives as a sibling of ``__init__.py`` so the themed check modules under
``checks/`` can import these without a circular dependency on the
top-level validator module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tripwire.core.enum_loader import EnumRegistry
    from tripwire.models.project import ProjectConfig


@dataclass
class CheckResult:
    """One finding from one check.

    Severity is `error` (blocks exit 0), `warning` (exit 1 unless --strict),
    or `fixed` (something the auto-fixer changed).
    """

    code: str
    severity: str  # "error" | "warning" | "fixed"
    message: str
    file: str | None = None
    line: int | None = None
    field: str | None = None
    fix_hint: str | None = None
    # For severity == "fixed"
    before: Any = None
    after: Any = None

    def to_json(self) -> dict[str, Any]:
        """Serialise to the JSON output schema."""
        out: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.file is not None:
            out["file"] = self.file
        if self.line is not None:
            out["line"] = self.line
        if self.field is not None:
            out["field"] = self.field
        if self.fix_hint is not None:
            out["fix_hint"] = self.fix_hint
        if self.severity == "fixed":
            out["before"] = self.before
            out["after"] = self.after
        return out


@dataclass
class ValidationReport:
    """The full output of `validate`."""

    version: int = 1
    exit_code: int = 0
    errors: list[CheckResult] = field(default_factory=list)
    warnings: list[CheckResult] = field(default_factory=list)
    fixed: list[CheckResult] = field(default_factory=list)
    cache_rebuilt: bool = False
    duration_ms: int = 0

    @property
    def findings(self) -> list[CheckResult]:
        """All findings, errors + warnings + fixed, in a single list."""
        return [*self.errors, *self.warnings, *self.fixed]

    @property
    def category_summary(self) -> dict[str, dict[str, int]]:
        """Group findings by category (the prefix before ``/``)."""
        cats: dict[str, dict[str, int]] = {}
        for finding in [*self.errors, *self.warnings, *self.fixed]:
            cat = finding.code.split("/")[0] if "/" in finding.code else finding.code
            if cat not in cats:
                cats[cat] = {"errors": 0, "warnings": 0, "fixed": 0}
            if finding.severity == "error":
                cats[cat]["errors"] += 1
            elif finding.severity == "warning":
                cats[cat]["warnings"] += 1
            elif finding.severity == "fixed":
                cats[cat]["fixed"] += 1
        return cats

    def to_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "exit_code": self.exit_code,
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "fixed": len(self.fixed),
                "cache_rebuilt": self.cache_rebuilt,
                "duration_ms": self.duration_ms,
            },
            "categories": self.category_summary,
            "errors": [e.to_json() for e in self.errors],
            "warnings": [w.to_json() for w in self.warnings],
            "fixed": [f.to_json() for f in self.fixed],
        }

    def to_summary(self) -> str:
        """One-line header + error-code counts.  Compact for agent consumption."""
        from collections import Counter

        lines: list[str] = []
        if self.exit_code == 0:
            lines.append("validate passed")
        else:
            lines.append(
                f"validate: {len(self.errors)} error(s), "
                f"{len(self.warnings)} warning(s)"
            )
        codes: Counter[str] = Counter()
        for e in self.errors:
            codes[e.code] += 1
        for w in self.warnings:
            codes[f"{w.code} (warning)"] += 1
        for code, count in codes.most_common():
            lines.append(f"  {code}: {count}")
        return "\n".join(lines)

    def to_compact(self) -> str:
        """One line per finding: ``file  code  message``."""
        lines: list[str] = []
        for finding in [*self.errors, *self.warnings]:
            file_part = finding.file or ""
            lines.append(f"{file_part}\t{finding.code}\t{finding.message}")
        return "\n".join(lines)


@dataclass
class LoadedEntity:
    """A successfully-loaded entity plus the path it came from."""

    rel_path: str
    raw_frontmatter: dict[str, Any]
    body: str
    model: Any  # Issue | ConceptNode | AgentSession | Comment


@dataclass
class ValidationContext:
    """Everything the validator loads up front, before running checks.

    Loading happens once and is shared across every check. Parse and schema
    errors that surface during load are collected here as `CheckResult`s
    so they appear in the final report alongside business-rule failures.
    """

    project_dir: Path
    project_config: ProjectConfig | None = None
    project_load_errors: list[CheckResult] = field(default_factory=list)

    issues: list[LoadedEntity] = field(default_factory=list)
    nodes: list[LoadedEntity] = field(default_factory=list)
    sessions: list[LoadedEntity] = field(default_factory=list)
    comments: list[LoadedEntity] = field(default_factory=list)

    issue_load_errors: list[CheckResult] = field(default_factory=list)
    node_load_errors: list[CheckResult] = field(default_factory=list)
    session_load_errors: list[CheckResult] = field(default_factory=list)
    comment_load_errors: list[CheckResult] = field(default_factory=list)

    enums: EnumRegistry = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.enums is None:
            from tripwire.core.enum_loader import EnumRegistry as _ER

            self.enums = _ER()

    def all_load_errors(self) -> list[CheckResult]:
        return [
            *self.project_load_errors,
            *self.issue_load_errors,
            *self.node_load_errors,
            *self.session_load_errors,
            *self.comment_load_errors,
        ]
