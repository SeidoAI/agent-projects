"""SpawnDefaults + SpawnConfig models."""

from pathlib import Path

import yaml

from tripwire.models.session import SpawnConfig
from tripwire.models.spawn import SpawnDefaults


def test_spawn_defaults_load_from_shipped():
    import tripwire

    path = Path(tripwire.__file__).parent / "templates" / "spawn" / "defaults.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = SpawnDefaults.model_validate(data)

    assert defaults.config.model == "opus"
    assert defaults.config.fallback_model == "sonnet"
    assert defaults.config.max_budget_usd == 100
    assert defaults.config.disallowed_tools == [
        "Agent",
        "AskUserQuestion",
        "SendUserMessage",
    ]
    assert "{plan}" in defaults.prompt_template
    assert "Resuming session" in defaults.resume_prompt_template


def test_spawn_defaults_empty_dict_fails_loud():
    """v0.14.0: SpawnDefaults has no Python-side field defaults; an
    empty dict (or any payload missing a required field) must raise
    ValidationError at construction. Tests the fail-loud principle —
    a malformed/incomplete spawn YAML can't silently fall back."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SpawnDefaults.model_validate({})


def test_spawn_config_session_override():
    sc = SpawnConfig(config={"model": "sonnet", "max_budget_usd": 10})
    assert sc.config["model"] == "sonnet"
    assert sc.prompt_template is None


def test_spawn_config_unknown_field_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SpawnConfig(nonsense="x")
