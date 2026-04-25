"""Tests for the pm-response.yaml.j2 artifact template (v0.7.9 §A3).

The PM authors this file after reading the agent's self-review.md
(rendered from self-review.md.j2). It must be parseable YAML — the
``pm_response_covers_self_review`` and ``pm_response_followups_resolve``
validator rules read it programmatically.

Spec §A3 schema:

    read_at: <iso-8601>
    read_by: pm
    items:
      - quote_excerpt: "<text from self-review item>"
        decision: accepted | deferred | re-engaged | rejected
        follow_up: KUI-XX        # required if decision == deferred
        fix_commit: <sha>        # required if decision == re-engaged
        note: "<one-line rationale>"
"""

from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

import tripwire

PACKAGE_TEMPLATE_DIR = Path(tripwire.__file__).parent / "templates" / "artifacts"


def _render_template(name: str, **ctx: object) -> str:
    env = Environment(
        loader=FileSystemLoader(str(PACKAGE_TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2", "yaml")),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env.get_template(name).render(**ctx)


class TestPmResponseTemplateExists:
    def test_template_file_present_in_package(self) -> None:
        assert (PACKAGE_TEMPLATE_DIR / "pm-response.yaml.j2").is_file(), (
            "pm-response.yaml.j2 must ship inside "
            "tripwire/templates/artifacts/ so scaffold can render it"
        )


class TestPmResponseTemplateRenders:
    def test_renders_valid_yaml(self) -> None:
        out = _render_template("pm-response.yaml.j2", session_id="s1")
        # Must parse as YAML — validator parses items[] from this file.
        data = yaml.safe_load(out)
        assert isinstance(data, dict)

    def test_yaml_has_required_top_level_keys(self) -> None:
        out = _render_template("pm-response.yaml.j2", session_id="s1")
        data = yaml.safe_load(out)
        assert "read_at" in data
        assert "read_by" in data
        assert "items" in data

    def test_items_is_a_list(self) -> None:
        out = _render_template("pm-response.yaml.j2", session_id="s1")
        data = yaml.safe_load(out)
        assert isinstance(data["items"], list), (
            "items must be a YAML list — validator iterates it"
        )

    def test_template_documents_decision_enum(self) -> None:
        """Comments in the rendered file must list the four decision
        values; PM is expected to look at the rendered file and pick
        one. If the spec adds a fifth decision, this test catches the
        forgotten template update."""
        out = _render_template("pm-response.yaml.j2", session_id="s1")
        for decision in ("accepted", "deferred", "re-engaged", "rejected"):
            assert decision in out, f"expected {decision!r} in template"

    def test_renders_without_session_id(self) -> None:
        out = _render_template("pm-response.yaml.j2")
        # Still must be valid YAML even without a session_id.
        data = yaml.safe_load(out)
        assert "items" in data
