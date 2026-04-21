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
    assert defaults.config.max_budget_usd == 50
    assert defaults.config.disallowed_tools == ["Agent"]
    assert "{plan}" in defaults.prompt_template


def test_spawn_defaults_minimal_roundtrip():
    # Empty dict accepts all defaults.
    defaults = SpawnDefaults.model_validate({})
    assert defaults.config.model == "opus"
    assert defaults.invocation.command == "claude"


def test_spawn_config_session_override():
    sc = SpawnConfig(config={"model": "sonnet", "max_budget_usd": 10})
    assert sc.config["model"] == "sonnet"
    assert sc.prompt_template is None


def test_spawn_config_unknown_field_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SpawnConfig(nonsense="x")
