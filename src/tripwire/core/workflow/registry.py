"""Implementation catalogs for workflow.yaml references.

``workflow.yaml`` owns placement: which validator, JIT prompt, prompt
check, or artifact belongs to which status. This module only answers
"which implementation ids exist?" and "which callable implements this
id?" so schema validation, transitions, and the UI can join configured
refs to executable code without hidden placement metadata.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from tripwire.core.workflow.loader import load_workflows


def validator_id_for(check_fn: Callable[..., object]) -> str:
    """Return the stable workflow id for a validator check function."""
    name = getattr(check_fn, "__name__", "")
    if name == "check":
        module_name = getattr(check_fn, "__module__", "")
        module_leaf = module_name.rsplit(".", 1)[-1]
        if module_leaf and module_leaf != module_name:
            return f"v_{module_leaf}"
    return f"v_{name.removeprefix('check_')}"


def validator_label_for(check_fn: Callable[..., object]) -> str:
    """Return the display label for a validator check function."""
    return validator_id_for(check_fn).removeprefix("v_").replace("_", " ")


def validator_description_for(check_fn: Callable[..., object]) -> str:
    """Return the first docstring paragraph for a validator."""
    text = inspect.getdoc(check_fn) or ""
    text = text.strip()
    if not text:
        return ""
    return text.split("\n\n", 1)[0].strip().replace("\n", " ")


def validator_catalog() -> dict[str, Callable[..., object]]:
    """Return all validator implementations keyed by workflow id."""
    from tripwire.core import validator

    catalog: dict[str, Callable[..., object]] = {}
    for check_fn in validator.ALL_CHECKS:
        catalog.setdefault(validator_id_for(check_fn), check_fn)
    return catalog


def known_validator_ids() -> set[str]:
    """Return all implemented validator ids."""
    return set(validator_catalog())


def validator_checks_for_ids(ids: Iterable[str]) -> list[Callable[..., object]]:
    """Return validator callables for *ids* in canonical ALL_CHECKS order."""
    wanted = set(ids)
    return [fn for vid, fn in validator_catalog().items() if vid in wanted]


def declared_validator_ids(project_dir: Path) -> list[str]:
    """Return the workflow.yaml-declared validator ids in first-seen order.

    ``v_workflow_well_formed`` is always prepended because it validates
    the source-of-truth file itself; every other validator must be
    listed under a workflow status to run by default.
    """
    ids: list[str] = ["v_workflow_well_formed"]
    spec = load_workflows(project_dir)
    if not spec.workflows:
        return list(validator_catalog())
    for workflow in spec.workflows.values():
        for route in workflow.routes:
            for validator_id in route.controls.tripwires:
                if validator_id not in ids:
                    ids.append(validator_id)
        for status in workflow.statuses:
            for validator_id in status.tripwires:
                if validator_id not in ids:
                    ids.append(validator_id)
    return ids


def known_jit_prompt_ids(project_dir: Path | None = None) -> set[str]:
    """Return implemented JIT prompt ids.

    Built-ins come from the packaged manifest. Project-local extras are
    included when *project_dir* is supplied and can be loaded.
    """
    from tripwire._internal.jit_prompts.loader import (
        _MANIFEST_PATH,
        _load_manifest,
        load_jit_prompt_registry,
    )

    ids = {
        str(entry["id"])
        for entries in _load_manifest(_MANIFEST_PATH).values()
        for entry in entries
        if isinstance(entry.get("id"), str)
    }
    if project_dir is None:
        return ids
    try:
        registry = load_jit_prompt_registry(project_dir)
    except Exception:
        return ids
    for prompts in registry.values():
        for prompt in prompts:
            ids.add(prompt.id)
    return ids


def jit_prompt_status_refs(
    project_dir: Path, jit_prompt_id: str
) -> list[tuple[str, str]]:
    """Return workflow.yaml statuses that reference *jit_prompt_id*."""
    refs: list[tuple[str, str]] = []
    spec = load_workflows(project_dir)
    for workflow in spec.workflows.values():
        for route in workflow.routes:
            if jit_prompt_id in route.controls.jit_prompts:
                refs.append((workflow.id, route.to_ref))
        for status in workflow.statuses:
            if jit_prompt_id in status.jit_prompts:
                refs.append((workflow.id, status.id))
    return refs


def known_prompt_check_ids(project_dir: Path) -> set[str]:
    """Return all implemented prompt-check slash command ids."""
    from tripwire.core.workflow.prompt_checks import collect_prompt_checks

    return {pc.id for pc in collect_prompt_checks(project_dir)}


def known_command_ids(project_dir: Path) -> set[str]:
    """Return all packaged or project-local slash command ids."""
    return known_prompt_check_ids(project_dir)


def known_skill_ids(project_dir: Path | None = None) -> set[str]:
    """Return packaged and project-local skill ids."""
    ids: set[str] = set()
    for root in _skill_roots(project_dir):
        if not root.is_dir():
            continue
        for skill_md in root.glob("*/SKILL.md"):
            ids.add(skill_md.parent.name)
    return ids


def _skill_roots(project_dir: Path | None) -> list[Path]:
    import tripwire

    roots = [Path(tripwire.__file__).parent / "templates" / "skills"]
    if project_dir is not None:
        roots.append(project_dir / ".tripwire" / "skills")
    return roots


def workflow_catalog_drift(project_dir: Path) -> list[dict[str, Any]]:
    """Return catalog/config mismatch findings for workflow-adjacent UIs.

    Referenced-missing controls are reported by ``validate_workflow_spec``.
    This helper reports implemented workflow controls that must be
    placed by ``workflow.yaml`` but are not referenced by any status.
    """
    spec = load_workflows(project_dir)
    if not spec.workflows:
        return []

    used_validators: set[str] = set()
    used_jit_prompts: set[str] = set()
    used_prompt_checks: set[str] = set()
    for workflow in spec.workflows.values():
        for route in workflow.routes:
            used_validators.update(route.controls.tripwires)
            used_jit_prompts.update(route.controls.jit_prompts)
            used_prompt_checks.update(route.controls.prompt_checks)
        for status in workflow.statuses:
            used_validators.update(status.tripwires)
            used_jit_prompts.update(status.jit_prompts)
            used_prompt_checks.update(status.prompt_checks)

    findings: list[dict[str, Any]] = []
    for ident in sorted(known_validator_ids() - used_validators):
        findings.append(
            {
                "source": "catalog",
                "code": "workflow/unreferenced_tripwire",
                "workflow": None,
                "status": None,
                "message": (
                    f"tripwire {ident!r} is implemented but not referenced in workflow.yaml"
                ),
                "severity": "warning",
            }
        )
    for ident in sorted(known_jit_prompt_ids(project_dir) - used_jit_prompts):
        findings.append(
            {
                "source": "catalog",
                "code": "workflow/unreferenced_jit_prompt",
                "workflow": None,
                "status": None,
                "message": (
                    f"JIT prompt {ident!r} is implemented but not referenced in workflow.yaml"
                ),
                "severity": "warning",
            }
        )

    from tripwire.core.workflow.prompt_checks import LIFECYCLE_PROMPT_CHECK_IDS

    for ident in sorted(LIFECYCLE_PROMPT_CHECK_IDS - used_prompt_checks):
        findings.append(
            {
                "source": "catalog",
                "code": "workflow/unreferenced_prompt_check",
                "workflow": None,
                "status": None,
                "message": (
                    f"prompt-check {ident!r} is implemented but not referenced in workflow.yaml"
                ),
                "severity": "warning",
            }
        )
    return findings


__all__ = [
    "declared_validator_ids",
    "jit_prompt_status_refs",
    "known_command_ids",
    "known_jit_prompt_ids",
    "known_prompt_check_ids",
    "known_skill_ids",
    "known_validator_ids",
    "validator_catalog",
    "validator_checks_for_ids",
    "validator_description_for",
    "validator_id_for",
    "validator_label_for",
    "workflow_catalog_drift",
]
