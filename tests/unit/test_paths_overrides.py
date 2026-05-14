"""Project override paths added in v0.7b (resolve_command_path, etc.)."""

from tripwire.core.paths import (
    project_commands_dir,
    project_spawn_dir,
    resolve_command_path,
    tripwire_dir,
)


def test_tripwire_dir_structure(tmp_path):
    assert tripwire_dir(tmp_path) == tmp_path / ".tripwire"
    assert project_commands_dir(tmp_path) == tmp_path / ".tripwire" / "commands"
    assert project_spawn_dir(tmp_path) == tmp_path / ".tripwire" / "spawn"


def test_resolve_command_falls_back_to_tripwire_default(tmp_path):
    result = resolve_command_path(tmp_path, "pm-scope")
    assert result.name == "pm-scope.md"
    # Must point into the installed tripwire package's templates dir.
    import tripwire

    expected_parent = (
        __import__("pathlib").Path(tripwire.__file__).parent / "templates" / "commands"
    )
    assert result.parent == expected_parent


def test_resolve_command_prefers_project_override(tmp_path):
    override_dir = tmp_path / ".tripwire" / "commands"
    override_dir.mkdir(parents=True)
    (override_dir / "pm-scope.md").write_text("# custom", encoding="utf-8")

    result = resolve_command_path(tmp_path, "pm-scope")
    assert result == override_dir / "pm-scope.md"
    assert result.read_text() == "# custom"


def test_resolve_command_unknown_name_returns_nonexistent_package_path(tmp_path):
    """If the command doesn't exist anywhere, return the tripwire-template path.

    The caller decides whether a missing file is an error. This keeps the
    resolver side-effect-free.
    """
    result = resolve_command_path(tmp_path, "does-not-exist")
    assert result.name == "does-not-exist.md"
    assert not result.exists()


# --- session_plan_path: subdir-canonical (KUI-158: flat-layout fallback removed) ---


def test_session_plan_path_returns_subdir_when_present(tmp_path):
    """Modern layout: plan.md under instances/sessions/<sid>/artifacts/."""
    from tripwire.core.paths import session_plan_path

    sd = tmp_path / "instances" / "sessions" / "s1"
    (sd / "artifacts").mkdir(parents=True)
    subdir_plan = sd / "artifacts" / "plan.md"
    subdir_plan.write_text("# subdir plan\n", encoding="utf-8")

    assert session_plan_path(tmp_path, "s1") == subdir_plan


def test_session_plan_path_returns_subdir_for_nonexistent_session(tmp_path):
    """No session dir on disk yet: resolver returns the subdir path (callers
    that need the file to actually exist check that themselves)."""
    from tripwire.core.paths import session_plan_path

    p = session_plan_path(tmp_path, "never-created")
    assert (
        p
        == tmp_path
        / "instances"
        / "sessions"
        / "never-created"
        / "artifacts"
        / "plan.md"
    )
    assert not p.exists()
