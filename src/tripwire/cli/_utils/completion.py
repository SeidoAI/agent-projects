"""`tripwire completion <shell>` — print shell completion install instructions.

Click ships with a built-in tab-completion mechanism that works for any
Click command. The user just needs to source the right snippet in their
shell rc file. This subcommand prints the snippet for `bash`, `zsh`, or
`fish` so the user can pipe it into their config or eval it in-place.

Once installed, completing a partial command (e.g. `tripwire val<TAB>`)
will offer the matching subcommands, and option completion works for
flags too.
"""

from __future__ import annotations

import click

SHELL_INSTRUCTIONS: dict[str, str] = {
    "bash": """\
# Bash completion for tripwire.
#
# To enable in your current shell, run:
#
#     eval "$(tripwire completion bash | tail -n 1)"
#
# To enable permanently, append the following line to ~/.bashrc:

eval "$(_TRIPWIRE_COMPLETE=bash_source tripwire)"
""",
    "zsh": """\
# Zsh completion for tripwire.
#
# To enable in your current shell, run:
#
#     eval "$(tripwire completion zsh | tail -n 1)"
#
# To enable permanently, append the following line to ~/.zshrc:

eval "$(_TRIPWIRE_COMPLETE=zsh_source tripwire)"
""",
    "fish": """\
# Fish completion for tripwire.
#
# To enable, save the snippet to your fish completions directory:
#
#     tripwire completion fish > ~/.config/fish/completions/tripwire.fish

_TRIPWIRE_COMPLETE=fish_source tripwire | source
""",
}


@click.command(name="completion")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion_cmd(shell: str) -> None:
    """Print instructions for installing shell tab completion.

    \b
    Examples:
        # Enable bash completion in the current shell
        eval "$(tripwire completion bash | tail -n 1)"

        # Permanently install zsh completion
        tripwire completion zsh >> ~/.zshrc

        # Install fish completion
        tripwire completion fish > ~/.config/fish/completions/tripwire.fish
    """
    click.echo(SHELL_INSTRUCTIONS[shell], nl=False)


__all__ = ["SHELL_INSTRUCTIONS", "completion_cmd"]
