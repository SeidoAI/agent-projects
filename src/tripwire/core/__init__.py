"""Stateless business logic for tripwire.

Modules in this package never hold mutable state across calls. They take
explicit `project_dir` arguments and operate on the filesystem.
"""
