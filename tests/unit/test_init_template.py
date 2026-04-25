"""Tests for the packaged init templates' invariants.

These tests pin the templates that `tripwire init` stamps into a new
project against the CLI's source-of-truth lists. The most important
invariant: the session-status enum must contain every value the CLI
actually emits, otherwise newly-init'd projects hit
`enum/session_status not in active session_status enum` validation
errors the moment a session runs (the v0.7.6 §B regression).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tripwire.templates import get_templates_dir

# Canonical session-status vocabulary the tripwire CLI emits, in the
# order listed by the v0.7.6 spec §2.B. Updated whenever a state is
# added to or removed from the lifecycle:
#
#   planned   — newly created, awaiting agenda
#   queued    — agenda finalised, awaiting executor pick-up
#   executing — agent running (set by `tripwire session spawn`)
#   paused    — execution paused (manual, or out of budget)
#   failed    — terminal failure
#   completed — execution finished, awaiting verification
#   done      — verified + closed
#
# The list is duplicated here intentionally — the test guards the
# template against drift even if the in-code enum class grows legacy
# values for backwards compatibility.
CANONICAL_SESSION_STATUSES: tuple[str, ...] = (
    "planned",
    "queued",
    "executing",
    "paused",
    "failed",
    "completed",
    "done",
)


def _load_template_enum(name: str) -> dict:
    """Load one of the packaged enum templates as a parsed dict."""
    path = get_templates_dir() / "enums" / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class TestSessionStatusEnumTemplate:
    """`templates/enums/session_status.yaml` is what every `tripwire
    init` stamps into a new project. Drift here is silent until a
    session runs against the new project; tests pin it explicitly."""

    def test_contains_canonical_session_statuses(self) -> None:
        data = _load_template_enum("session_status")
        ids = {entry["id"] for entry in data["values"]}
        canonical = set(CANONICAL_SESSION_STATUSES)

        missing = canonical - ids
        assert not missing, (
            f"Template enums/session_status.yaml is missing canonical "
            f"CLI-emitted statuses: {sorted(missing)}. New projects will "
            f"hit `enum/session_status` validation errors."
        )

    def test_does_not_ship_legacy_statuses(self) -> None:
        """Legacy values were removed in v0.7.6 §B. Re-introducing them
        in the template would re-stake the v0.7.5 paint job — projects
        would see them as "valid" when in fact the CLI never emits them."""
        legacy = {
            "active",
            "waiting_for_ci",
            "waiting_for_review",
            "waiting_for_deploy",
            "re_engaged",
            "in_review",
            "verified",
            "abandoned",
        }
        data = _load_template_enum("session_status")
        ids = {entry["id"] for entry in data["values"]}
        leaked = ids & legacy
        assert not leaked, (
            f"Template enums/session_status.yaml ships legacy values "
            f"{sorted(leaked)}. v0.7.6 §B explicitly drops them — they "
            f"are not in the CLI's emitted vocabulary."
        )

    def test_every_entry_has_id_label_color(self) -> None:
        """Sanity: each value entry has the three fields the UI relies
        on. Missing ones surface as KeyError at render time."""
        data = _load_template_enum("session_status")
        for entry in data["values"]:
            assert {"id", "label", "color"} <= entry.keys(), entry

    def test_template_path_exists(self) -> None:
        """The packaged templates dir must contain the file. Catches the
        case where wheel packaging strips it accidentally."""
        path: Path = get_templates_dir() / "enums" / "session_status.yaml"
        assert path.is_file(), f"Missing packaged template: {path}"


class TestCIWorkflowTemplate:
    """`templates/project/.github/workflows/tripwire.yml.j2` is what
    `tripwire init` stamps as the project's CI gate. The action
    versions need to match v0.7.6 §2.E.1 — Node 20 is being removed
    from runners 2026-09-16 and `setup-uv@v3` rejects `python-version`
    after a schema change."""

    def test_uses_pinned_action_versions(self) -> None:
        path = (
            get_templates_dir()
            / "project"
            / ".github"
            / "workflows"
            / "tripwire.yml.j2"
        )
        contents = path.read_text(encoding="utf-8")
        # `actions/checkout@v6` — bumped from v4 (Node 20 deprecation).
        assert "actions/checkout@v6" in contents, contents
        # `astral-sh/setup-uv@v8.1.0` — point release, not floating @v8.
        assert "astral-sh/setup-uv@v8.1.0" in contents, contents
        # And nothing's still on the old majors.
        assert "actions/checkout@v4" not in contents, "checkout@v4 leaked back in"
        assert "astral-sh/setup-uv@v3" not in contents, "setup-uv@v3 leaked back in"
