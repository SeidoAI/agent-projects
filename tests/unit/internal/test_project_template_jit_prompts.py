"""The default project.yaml.j2 must render a `tripwires:` block.

Without this, freshly-initialised projects have no `tripwires:` field
and the load_project pydantic model uses its defaults — which works,
but the AC requires the block to be visible in the rendered file so
operators can edit it.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

import tripwire


def _render() -> str:
    template_dir = Path(tripwire.__file__).parent / "templates" / "project"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    template = env.get_template("project.yaml.j2")
    return template.render(
        project_name="example-project",
        key_prefix="EXM",
        description="",
        base_branch="main",
        repos=None,
        repos_locals={},
        created_at="2026-04-26T15:00:00",
        tripwire_version="0.8.0",
        project_repo_url=None,
    )


def test_rendered_project_yaml_has_tripwires_block() -> None:
    rendered = _render()
    parsed = yaml.safe_load(rendered)
    assert "tripwires" in parsed
    assert parsed["tripwires"] == {
        "enabled": True,
        "opt_out": [],
        "extra": [],
    }


def test_rendered_project_yaml_round_trips_through_project_model() -> None:
    """The rendered YAML must parse cleanly through ProjectConfig.

    `extra="forbid"` would block any unknown key, so this is the
    canonical contract test that the rendered tripwires block matches
    the typed model surface.
    """
    from tripwire.models.project import ProjectConfig

    rendered = _render()
    parsed = yaml.safe_load(rendered)
    project = ProjectConfig.model_validate(parsed)
    assert project.tripwires.enabled is True
    assert project.tripwires.opt_out == []
    assert project.tripwires.extra == []
