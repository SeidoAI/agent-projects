"""External CLI wrappers (gh, git).

Click subcommands organized as external-tool wrappers; each module
registers itself with ``cli.add_command`` in ``main.py``. The
``_tools/`` prefix is internal organization, not part of the
user-facing CLI surface — users still invoke ``tripwire gh ...`` and
``tripwire git ...``.
"""
