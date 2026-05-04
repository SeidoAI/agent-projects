"""Build the workflow territory payload for `/api/workflow`.

The canonical topology is `workflow.yaml`. This service parses that file,
joins shallow registry metadata for referenced controls, and returns the
workflow-first shape consumed by the Workflow page.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from tripwire.core.workflow.drift import detect_drift
from tripwire.core.workflow.loader import load_workflows
from tripwire.core.workflow.prompt_checks import collect_prompt_checks
from tripwire.core.workflow.registry import (
    known_command_ids,
    known_jit_prompt_ids,
    known_skill_ids,
    validator_catalog,
    validator_description_for,
    validator_label_for,
    workflow_catalog_drift,
)
from tripwire.core.workflow.schema import (
    Workflow,
    WorkflowArtifactRef,
    WorkflowFinding,
    WorkflowRoute,
    validate_workflow_spec,
)
from tripwire.ui.services.role_gate import (
    PROMPT_REDACTED_PLACEHOLDER,
    redact_jit_prompt,
)


def build_workflow(
    project_dir: Path,
    *,
    project_id: str,
    is_pm_role: bool,
) -> dict[str, Any]:
    """Build the `/api/workflow` response for *project_dir*."""
    spec = load_workflows(project_dir)
    registry = _build_registry(
        project_dir,
        project_id=project_id,
        is_pm_role=is_pm_role,
    )
    definition_findings = validate_workflow_spec(
        spec,
        known_validators={entry["id"] for entry in registry["validators"]},
        known_jit_prompts={entry["id"] for entry in registry["jit_prompts"]},
        known_prompt_checks={entry["id"] for entry in registry["prompt_checks"]},
        known_commands={entry["id"] for entry in registry["commands"]},
        known_skills={entry["id"] for entry in registry["skills"]},
    )
    runtime_findings = detect_drift(project_dir)
    drift_findings = [
        *_workflow_findings_to_dicts(definition_findings),
        *workflow_catalog_drift(project_dir),
        *[_runtime_drift_to_dict(finding) for finding in runtime_findings],
    ]

    return {
        "project_id": project_id,
        "workflows": [_workflow_to_dict(wf) for wf in spec.workflows.values()],
        "registry": registry,
        "drift": {
            "count": len(drift_findings),
            "findings": drift_findings,
        },
    }


def _workflow_to_dict(workflow: Workflow) -> dict[str, Any]:
    return {
        "id": workflow.id,
        "actor": workflow.actor,
        "trigger": workflow.trigger,
        "brief_description": workflow.brief_description,
        "statuses": [
            {
                "id": status.id,
                "label": status.id.replace("_", " "),
                "next": _next_spec_to_dict(status.next),
                "validators": list(status.validators),
                "jit_prompts": list(status.jit_prompts),
                "prompt_checks": list(status.prompt_checks),
                "artifacts": {
                    "produces": [
                        _artifact_ref_to_dict(ref) for ref in status.artifacts.produces
                    ],
                    "consumes": [
                        _artifact_ref_to_dict(ref) for ref in status.artifacts.consumes
                    ],
                },
                "work_steps": [
                    {
                        "id": ws.id,
                        "actor": ws.actor,
                        "label": ws.label,
                        "skills": list(ws.skills),
                    }
                    for ws in status.work_steps
                ],
                "cross_links": [
                    {
                        "workflow": link.workflow,
                        "status": link.status,
                        "label": link.label,
                        "kind": link.kind,
                    }
                    for link in status.cross_links
                ],
            }
            for status in workflow.statuses
        ],
        "routes": [_route_to_dict(workflow.id, route) for route in workflow.routes],
    }


def _artifact_ref_to_dict(ref: WorkflowArtifactRef) -> dict[str, Any]:
    out: dict[str, Any] = {"id": ref.id, "label": ref.label}
    if ref.path:
        out["path"] = ref.path
    return out


def _route_to_dict(workflow_id: str, route: WorkflowRoute) -> dict[str, Any]:
    return {
        "id": route.id,
        "workflow_id": workflow_id,
        "actor": route.actor,
        "from": route.from_ref,
        "to": route.to_ref,
        "kind": route.kind,
        "label": route.label,
        "trigger": route.trigger,
        "command": route.command,
        "controls": {
            "validators": list(route.controls.validators),
            "jit_prompts": list(route.controls.jit_prompts),
            "prompt_checks": list(route.controls.prompt_checks),
        },
        "skills": list(route.skills),
        "emits": {
            "artifacts": [_artifact_ref_to_dict(ref) for ref in route.emits.artifacts],
            "events": list(route.emits.events),
            "comments": list(route.emits.comments),
            "status_changes": list(route.emits.status_changes),
        },
    }


def _next_spec_to_dict(next_spec: Any) -> dict[str, Any]:
    kind = next_spec.kind
    if kind == "single":
        return {"kind": "single", "single": next_spec.single}
    if kind == "conditional":
        branches: list[dict[str, Any]] = []
        for branch in next_spec.conditional or []:
            if branch.predicate is None:
                branches.append({"else": branch.then})
            else:
                pred = branch.predicate
                branches.append(
                    {"if": f"{pred.field} {pred.op} {pred.value}", "then": branch.then}
                )
        return {"kind": "conditional", "branches": branches}
    return {"kind": "terminal"}


def _build_registry(
    project_dir: Path,
    *,
    project_id: str,
    is_pm_role: bool,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "validators": _build_validator_registry(),
        "jit_prompts": _build_jit_prompt_registry(
            project_dir,
            project_id=project_id,
            is_pm_role=is_pm_role,
        ),
        "prompt_checks": _build_prompt_check_registry(project_dir),
        "commands": _build_command_registry(project_dir),
        "skills": _build_skill_registry(project_dir),
    }


def _build_validator_registry() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for validator_id, fn in validator_catalog().items():
        if validator_id in seen:
            continue
        seen.add(validator_id)
        try:
            src = inspect.getfile(fn)
        except (TypeError, OSError):
            src = ""
        entry: dict[str, Any] = {
            "id": validator_id,
            "label": validator_label_for(fn),
            "description": validator_description_for(fn),
            "source": src,
            "blocking": True,
        }
        out.append(entry)
    return out


def _build_jit_prompt_registry(
    project_dir: Path,
    *,
    project_id: str,
    is_pm_role: bool,
) -> list[dict[str, Any]]:
    from tripwire._internal.jit_prompts import JitPromptContext
    from tripwire._internal.jit_prompts.loader import load_jit_prompt_registry

    ctx = JitPromptContext(
        project_dir=project_dir,
        project_id=project_id,
        session_id="__workflow_map__",
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event, prompts in load_jit_prompt_registry(project_dir).items():
        for prompt in prompts:
            if prompt.id in seen:
                continue
            seen.add(prompt.id)
            prompt_body = _safe_prompt_body(prompt, ctx)
            revealed, redacted = redact_jit_prompt(
                prompt=prompt_body,
                is_pm_role=is_pm_role,
            )
            entry: dict[str, Any] = {
                "id": prompt.id,
                "label": prompt.id.replace("-", " "),
                "description": _first_paragraph(inspect.getdoc(prompt.__class__) or ""),
                "blocking": bool(prompt.blocks),
                "fires_on_event": event,
                "prompt_revealed": revealed,
                "prompt_redacted": redacted or PROMPT_REDACTED_PLACEHOLDER,
            }
            out.append(entry)
    for prompt_id in sorted(known_jit_prompt_ids(project_dir) - seen):
        out.append(
            {
                "id": prompt_id,
                "label": prompt_id.replace("-", " "),
                "description": "",
                "blocking": True,
                "fires_on_event": None,
                "prompt_revealed": None,
                "prompt_redacted": PROMPT_REDACTED_PLACEHOLDER,
            }
        )
    return out


def _safe_prompt_body(prompt: Any, ctx: Any) -> str:
    try:
        return str(prompt.fire(ctx))
    except Exception:
        return ""


def _build_prompt_check_registry(project_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for prompt_check in collect_prompt_checks(project_dir):
        out.append(
            {
                "id": prompt_check.id,
                "label": prompt_check.id.replace("-", " "),
                "description": prompt_check.description,
                "source": str(prompt_check.source),
                "blocking": True,
            }
        )
    return out


def _build_command_registry(project_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for command in collect_prompt_checks(project_dir):
        out.append(
            {
                "id": command.id,
                "label": command.id.replace("-", " "),
                "description": command.description,
                "source": str(command.source),
                "blocking": False,
            }
        )
    # Keep this defensive: if future command discovery differs from
    # prompt-check discovery, route validation can still resolve the id.
    for command_id in sorted(
        known_command_ids(project_dir) - {entry["id"] for entry in out}
    ):
        out.append(
            {
                "id": command_id,
                "label": command_id.replace("-", " "),
                "description": "",
                "source": "",
                "blocking": False,
            }
        )
    return out


def _build_skill_registry(project_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for skill_id in sorted(known_skill_ids(project_dir)):
        source = _skill_source(project_dir, skill_id)
        out.append(
            {
                "id": skill_id,
                "label": skill_id.replace("-", " "),
                "description": _skill_description(source) if source else "",
                "source": str(source) if source else "",
                "blocking": False,
            }
        )
    return out


def _skill_source(project_dir: Path, skill_id: str) -> Path | None:
    import tripwire

    candidates = [
        project_dir / ".tripwire" / "skills" / skill_id / "SKILL.md",
        Path(tripwire.__file__).parent / "templates" / "skills" / skill_id / "SKILL.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _skill_description(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for paragraph in text.split("\n\n"):
        cleaned = paragraph.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        return cleaned.replace("\n", " ")
    return ""


def _workflow_findings_to_dicts(
    findings: list[WorkflowFinding],
) -> list[dict[str, Any]]:
    return [
        {
            "source": "definition",
            "code": finding.code,
            "workflow": finding.workflow,
            "status": finding.status,
            "message": finding.message,
            "severity": finding.severity,
        }
        for finding in findings
    ]


def _runtime_drift_to_dict(finding: Any) -> dict[str, Any]:
    return {
        "source": "runtime",
        "code": finding.code,
        "workflow": finding.workflow,
        "instance": finding.instance,
        "status": finding.status,
        "message": finding.message,
        "severity": finding.severity,
    }


def _first_paragraph(text: str) -> str:
    """Return the first non-empty paragraph of *text*."""
    text = text.strip()
    if not text:
        return ""
    return text.split("\n\n", 1)[0].strip().replace("\n", " ")


__all__ = ["build_workflow"]
