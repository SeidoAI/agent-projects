"""Genuinely cross-entity Click commands.

Click subcommands organized as cross-entity commands; each module
registers itself with ``cli.add_command`` in ``main.py``. The
``_cross/`` prefix is internal organization, not part of the
user-facing CLI surface — these stay as top-level commands such as
``tripwire transition``.
"""
