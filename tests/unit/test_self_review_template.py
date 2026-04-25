"""Tests for the self-review.md.j2 artifact template (v0.7.9 §A2).

The template ships in ``src/tripwire/templates/artifacts/`` so
``tripwire session scaffold <sid> --artifact self-review.md`` can
render it. The four-lens schema is fixed; the validator's
``pm_response_covers_self_review`` rule (KUI-86) parses the rendered
file looking for ``## Lens N:`` headings.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

import tripwire

PACKAGE_TEMPLATE_DIR = Path(tripwire.__file__).parent / "templates" / "artifacts"


def _render_template(name: str, **ctx: object) -> str:
    env = Environment(
        loader=FileSystemLoader(str(PACKAGE_TEMPLATE_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2", "md")),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env.get_template(name).render(**ctx)


class TestSelfReviewTemplateExists:
    def test_template_file_present_in_package(self) -> None:
        assert (PACKAGE_TEMPLATE_DIR / "self-review.md.j2").is_file(), (
            "self-review.md.j2 must ship inside "
            "tripwire/templates/artifacts/ so scaffold can render it"
        )


class TestSelfReviewTemplateRenders:
    def test_renders_with_session_id_in_heading(self) -> None:
        out = _render_template("self-review.md.j2", session_id="my-session")
        assert "Self-review" in out
        assert "my-session" in out

    def test_renders_all_four_lenses(self) -> None:
        out = _render_template("self-review.md.j2", session_id="s1")
        assert "## Lens 1:" in out
        assert "## Lens 2:" in out
        assert "## Lens 3:" in out
        assert "## Lens 4:" in out

    def test_lens_headings_match_spec(self) -> None:
        """The validator (and PM) parse on these specific lens names —
        renaming a lens silently breaks downstream coverage checks."""
        out = _render_template("self-review.md.j2", session_id="s1")
        assert "AC met but not really" in out
        assert "Unilateral decisions" in out
        assert "Skipped workflow" in out
        assert "Quality degradation over time" in out

    def test_renders_without_session_id_uses_placeholder(self) -> None:
        """Render must not blow up if session_id isn't passed — useful
        when scaffold is invoked outside a session context (e.g. CI
        smoke tests)."""
        out = _render_template("self-review.md.j2")
        assert "Self-review" in out
