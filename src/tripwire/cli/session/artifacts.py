"""``tripwire session artifacts`` — alias for ``tripwire artifacts list``."""

from __future__ import annotations

from tripwire.cli.artifacts import artifacts_list
from tripwire.cli.session._group import session_cmd

# Alias `tripwire session artifacts <id>` to the existing
# `tripwire artifacts list <id>`. Uses `add_command` (not the
# `@session_cmd.command` decorator) because we're re-mounting an
# already-defined Click command under a different parent group.
session_cmd.add_command(artifacts_list, name="artifacts")
