"""Click CLI entry points for tripwire.

The v0 surface is intentionally minimal: read commands, validation, and
atomic operations only. Mutation commands (`issue create`, `node create`,
etc.) are deferred — agents create entities by writing files directly.
"""
