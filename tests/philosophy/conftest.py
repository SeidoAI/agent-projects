"""Shared fixtures for philosophy tests.

Philosophy tests need very small, deliberately-shaped tripwire
projects — usually one workflow, one instance, nothing else. The
suite-wide ``tmp_path_project`` fixture in ``tests/conftest.py``
pulls in the full coding-session workflow with every implemented
validator referenced; that's the right default for the unit /
integration suites but it's noise for a test whose job is to prove
*"a single workflow declared in YAML works"*.

These fixtures keep philosophy tests reading like specs: ``project
declares X workflow with Y statuses, instance file lives at Z, run
transition, assert Z's status changed``.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import yaml

PROJECT_YAML_MINIMAL = dedent(
    """\
    name: phil
    key_prefix: PHL
    next_issue_number: 1
    next_session_number: 1
    repos:
      SeidoAI/phil:
        local: null
    """
)


@pytest.fixture
def minimal_project(tmp_path: Path) -> Path:
    """Return a tripwire project root with project.yaml + the
    ``instances/`` skeleton — but **no** workflow.yaml.

    Tests that exercise a single workflow append their own
    ``workflow.yaml`` so the YAML reads as a spec for *that* test,
    not a noisy carryover from a shared template.
    """
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "project.yaml").write_text(PROJECT_YAML_MINIMAL, encoding="utf-8")
    for sub in (
        "instances",
        "instances/issues",
        "instances/nodes",
        "instances/sessions",
    ):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    return project_dir


def write_workflow_yaml(project_dir: Path, workflows: dict) -> None:
    """Write a workflow.yaml with the given ``{workflow_id: {...}}`` mapping.

    ``workflow_schema_version`` is added automatically. Each value is the
    workflow body (statuses, routes, instance block, etc.) — pure dict, no
    Jinja, no string-template assembly. This keeps each test's workflow
    declaration legible as a YAML spec.
    """
    payload = {"workflow_schema_version": 1, "workflows": workflows}
    (project_dir / "workflow.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )


def write_instance_file(
    project_dir: Path, storage_path_template: str, instance_id: str, data: dict
) -> Path:
    """Materialise an instance file at the declared ``storage_path``.

    ``storage_path_template`` is the workflow's ``instance.storage_path``
    string with ``{instance_id}`` to interpolate. The file is written as
    YAML frontmatter + empty body, matching the format
    ``instance_io.load_instance`` parses.
    """
    rendered = storage_path_template.format(instance_id=instance_id)
    target = project_dir / rendered
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = yaml.safe_dump(data, sort_keys=False)
    target.write_text(f"---\n{frontmatter}---\n", encoding="utf-8")
    return target
