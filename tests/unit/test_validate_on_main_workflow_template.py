"""Verify the v0.7.9 §A10 ``validate-on-main.yml.j2`` workflow template
renders to valid YAML, pins actions to point releases, and runs
``tripwire validate --strict`` on push and PR.
"""

from __future__ import annotations

import yaml
from jinja2 import Environment, FileSystemLoader

from tripwire.templates import get_templates_dir


def _render_template(version: str = "0.7.9") -> str:
    template_root = get_templates_dir() / "project" / ".github" / "workflows"
    env = Environment(
        loader=FileSystemLoader(str(template_root)),
        keep_trailing_newline=True,
    )
    return env.get_template("validate-on-main.yml.j2").render(
        tripwire_version=version
    )


def test_template_renders_to_valid_yaml():
    rendered = _render_template()
    data = yaml.safe_load(rendered)
    assert data["name"] == "tripwire validate"
    # YAML 1.1: bareword ``on`` parses as boolean True.
    on_block = data[True]
    assert "main" in on_block["push"]["branches"]
    assert "main" in on_block["pull_request"]["branches"]
    assert data["jobs"]["validate"]["runs-on"] == "ubuntu-latest"


def test_template_runs_tripwire_validate_strict():
    rendered = _render_template()
    assert "tripwire validate --strict" in rendered


def test_template_pins_third_party_actions_to_point_releases():
    rendered = _render_template()
    assert "actions/checkout@v6" in rendered
    assert "astral-sh/setup-uv@v8.1.0" in rendered


def test_template_stamps_tripwire_version():
    rendered = _render_template("0.7.9")
    assert "tripwire-pm" in rendered
    assert "0.7.9" in rendered


def test_template_has_timeout():
    """A 5-min timeout per §A10 — keeps pathological runs from
    burning CI minutes."""
    rendered = _render_template()
    data = yaml.safe_load(rendered)
    assert data["jobs"]["validate"]["timeout-minutes"] == 5
