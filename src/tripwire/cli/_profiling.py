"""Optional cProfile wrapping for CLI commands.

The agent's most-invoked command is `validate`. When investigating slow
runs, wrap any decorated command with `--profile[=PATH]` to dump a
`cProfile` output file. Defaults to `.tripwire.profile` in the cwd
with a hint about inspecting it via `snakeviz` or `python -m pstats`.

Usage:

    @click.command()
    @profileable
    def my_cmd(...) -> None:
        ...

The decorator MUST be applied AFTER `@click.command()` and BEFORE any
other Click options on the same function so that Click sees the new
`--profile` option in its option list.
"""

from __future__ import annotations

import cProfile
import functools
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

DEFAULT_PROFILE_PATH = ".tripwire.profile"


def profileable(command: Callable[..., Any]) -> Callable[..., Any]:
    """Add a `--profile[=PATH]` option to a Click command.

    When `--profile` is passed without a value, dumps to
    `.tripwire.profile`. When passed with a value (`--profile=foo.prof`),
    dumps to that path. When omitted entirely, runs the command unwrapped.

    A hint about inspecting the profile is printed to stderr after the
    wrapped command completes.
    """

    @click.option(
        "--profile",
        "profile_path",
        type=click.Path(path_type=Path),
        default=None,
        is_flag=False,
        flag_value=DEFAULT_PROFILE_PATH,
        help=(
            "Run the command under cProfile and dump the output to this "
            f"path (default: {DEFAULT_PROFILE_PATH}). Inspect with "
            "`snakeviz` or `python -m pstats`."
        ),
    )
    @functools.wraps(command)
    def wrapper(*args: Any, profile_path: Path | None, **kwargs: Any) -> Any:
        if profile_path is None:
            return command(*args, **kwargs)
        profiler = cProfile.Profile()
        profiler.enable()
        try:
            return command(*args, **kwargs)
        finally:
            profiler.disable()
            profiler.dump_stats(str(profile_path))
            click.echo(
                f"Profile written to {profile_path}. "
                f"Inspect with: snakeviz {profile_path}",
                err=True,
            )

    return wrapper


__all__ = ["DEFAULT_PROFILE_PATH", "profileable"]
