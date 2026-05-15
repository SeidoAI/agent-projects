"""Tripwire is filesystem-native. No DB. No service-backed persistence.

Philosophy §7 ("Filesystem-native, file-watcher transport") makes
this load-bearing:

    *"Tripwire is git-native: every entity is a file, every change is
    a commit, every audit is `git log` or `git blame`. This shapes
    the runtime architecture too."*

If a future agent adds a SQL database, a Redis cache, or an HTTP-backed
state store for "performance" or "cleaner querying," every §7 promise
breaks at once: ``git blame inbox/`` stops working, the file-watcher
transport ceases to be the source of truth, audits no longer match
the on-disk shape, and the framework starts requiring a side-car
service to be installed before it can run.

This fitness function pins the discipline: ``src/tripwire/`` contains
no imports of database or persistence-service client libraries.

Carve-outs (allowed imports the test deliberately doesn't flag):

  - ``subprocess`` — fine for talking to ``gh`` / ``git`` CLIs.
  - ``httpx`` / ``requests`` for outbound HTTP — fine for talking to
    GitHub / external review services. The §7 forbidden shape is
    *persistence* via the network, not *communication* via the
    network. If a follow-up wants to scan for ``requests.post`` etc.
    as a stricter "no outbound HTTP from core" rule, that's a
    separate fitness function.
"""

from __future__ import annotations

import re
from pathlib import Path

import tripwire

SRC_ROOT = Path(tripwire.__file__).parent

# Module names whose import in src/tripwire would indicate a
# persistence-service dependency. Each is a hard `from X import …` or
# `import X` shape — substring match is fine because these names are
# distinctive.
FORBIDDEN_PERSISTENCE_IMPORTS = {
    "sqlalchemy",
    "sqlmodel",
    "psycopg",
    "psycopg2",
    "asyncpg",
    "aiosqlite",
    "sqlite3",
    "pymongo",
    "motor",  # async MongoDB
    "redis",
    "aioredis",
    "boto3",
    "google.cloud.storage",
    "google.cloud.firestore",
    "google.cloud.datastore",
    "elasticsearch",
    "opensearch",
}

IMPORT_PATTERN = re.compile(
    r"^\s*(?:from\s+(\S+)|import\s+(\S+))",
    re.MULTILINE,
)


def _imports_in(text: str) -> set[str]:
    """Return all top-level imported module names appearing in *text*."""
    out: set[str] = set()
    for match in IMPORT_PATTERN.finditer(text):
        name = match.group(1) or match.group(2)
        if name is None:
            continue
        # Strip submodule path — `from sqlalchemy.orm import X` →
        # `sqlalchemy`.
        out.add(name.split(".")[0])
    return out


def test_src_imports_no_database_or_persistence_service():
    """No persistence-service client appears as an import in
    ``src/tripwire/``.

    The §7 promise is that the framework runs against a project
    directory and nothing else. Introducing a DB / cache / cloud
    storage dependency breaks that — projects suddenly need
    infrastructure to operate.
    """
    violations: list[str] = []
    for py_file in SRC_ROOT.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        names = _imports_in(text)
        for forbidden in FORBIDDEN_PERSISTENCE_IMPORTS:
            top = forbidden.split(".")[0]
            if top in names:
                rel = py_file.relative_to(SRC_ROOT.parent)
                violations.append(f"  {rel}: imports {forbidden!r}")
                break

    assert not violations, (
        "Philosophy §7 violation — src/tripwire/ imports a persistence-\n"
        "service client. Tripwire is filesystem-native: every entity is a\n"
        "file, every audit is `git log`. A DB/cache/cloud-store import\n"
        "breaks that contract.\n"
        "\n"
        "Offending imports:\n" + "\n".join(violations) + "\n"
        "\n"
        "Fix: persist state to files under the project directory. If a\n"
        "use case genuinely needs queryable storage (e.g. fast lookups),\n"
        "the §7-compatible pattern is a derived cache file (like\n"
        "`nodes/tripwire-graph-index.yaml`) rebuilt from the source-of-\n"
        "truth files on demand — not a side-car database."
    )
