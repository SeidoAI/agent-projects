"""`tripwire config` — read and write ``~/.tripwire/config.yaml``.

Provides ergonomic subcommands so users don't have to hand-edit YAML.
The config file is single-user, machine-local, and only consulted by
``tripwire ui`` (project + workspace discovery roots, port, etc.).
"""

from __future__ import annotations

from pathlib import Path

import click
import yaml

from tripwire.ui.config import (
    _DEFAULT_CONFIG_PATH,
    load_user_config,
    save_user_config,
)


@click.group(name="config")
def config_cmd() -> None:
    """Manage ``~/.tripwire/config.yaml``."""


@config_cmd.command("show")
@click.option(
    "--path",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Read from this path instead of ~/.tripwire/config.yaml.",
)
def config_show_cmd(config_path: Path | None) -> None:
    """Print the resolved user config as YAML."""
    config = load_user_config(config_path)
    payload = config.model_dump(mode="json", exclude_none=True)
    target = config_path if config_path is not None else _DEFAULT_CONFIG_PATH
    click.echo(f"# {target}")
    click.echo(yaml.safe_dump(payload, sort_keys=True).rstrip())


@config_cmd.command("set")
@click.argument("key", type=click.Choice(["project-roots", "workspace-roots"]))
@click.argument("paths", nargs=-1, required=True, type=click.Path(path_type=Path))
def config_set_cmd(key: str, paths: tuple[Path, ...]) -> None:
    """Overwrite a list-valued config key.

    Example:
        tripwire config set project-roots ~/Code/seido/tripwire/projects
    """
    config = load_user_config()
    expanded = [Path(p).expanduser() for p in paths]
    field = key.replace("-", "_")
    if field == "project_roots":
        config = config.model_copy(update={"project_roots": expanded})
    elif field == "workspace_roots":
        config = config.model_copy(update={"workspace_roots": expanded})
    else:  # pragma: no cover — Choice prevents this
        raise click.UsageError(f"Unsupported key: {key}")
    written_to = save_user_config(config)
    click.echo(f"Wrote {key} to {written_to}")
    for p in expanded:
        if not p.exists():
            click.echo(f"  warning: {p} does not exist", err=True)


@config_cmd.command("add")
@click.argument("key", type=click.Choice(["project-root", "workspace-root"]))
@click.argument("path", type=click.Path(path_type=Path))
def config_add_cmd(key: str, path: Path) -> None:
    """Append a single path to a list-valued config key.

    Example:
        tripwire config add project-root ~/Code/seido/tripwire/projects
    """
    config = load_user_config()
    expanded = Path(path).expanduser()
    if key == "project-root":
        existing = list(config.project_roots)
        if expanded.resolve() in {p.resolve() for p in existing}:
            click.echo(f"{expanded} already in project_roots; nothing to do.")
            return
        existing.append(expanded)
        config = config.model_copy(update={"project_roots": existing})
        list_name = "project_roots"
    elif key == "workspace-root":
        existing = list(config.workspace_roots)
        if expanded.resolve() in {p.resolve() for p in existing}:
            click.echo(f"{expanded} already in workspace_roots; nothing to do.")
            return
        existing.append(expanded)
        config = config.model_copy(update={"workspace_roots": existing})
        list_name = "workspace_roots"
    else:  # pragma: no cover
        raise click.UsageError(f"Unsupported key: {key}")
    written_to = save_user_config(config)
    click.echo(f"Appended to {list_name} in {written_to}")
    if not expanded.exists():
        click.echo(f"  warning: {expanded} does not exist", err=True)


@config_cmd.command("path")
def config_path_cmd() -> None:
    """Print the path tripwire reads its config from."""
    click.echo(str(_DEFAULT_CONFIG_PATH))


__all__ = ["config_cmd"]
