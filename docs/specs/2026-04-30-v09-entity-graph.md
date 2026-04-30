# v0.9 entity-graph substrate

Status: shipped (KUI-126, KUI-127, KUI-128, KUI-130, KUI-131, KUI-132,
KUI-133, KUI-134)
Authors: backend-coder agent (session `v09-entity-graph-substrate`)
Date: 2026-04-30

## Why

Before v0.9, `graph/index.yaml` carried two entity types (issues and
concept nodes) and a fixed set of legacy edge type strings
(`references`, `blocked_by`, `blocks`, `implements`, `parent`,
`related`, `source`). Each entity type had bespoke validation in
`core/validator/checks/references.py`, and the inverse direction of
each edge was either stored (`blocks`) or computed ad hoc.

v0.9 unifies the substrate so that every project-level entity —
issues, sessions, decisions, comments, pull requests, tripwire
instances, plus the existing concept nodes — is a node in a single
index, and every edge between them runs through one canonical
taxonomy.

## What

### Entity types (`NodeKind`)

The 7 canonical entity types carried as nodes:

| Kind                | Source of truth                                     |
| ------------------- | --------------------------------------------------- |
| `concept-node`      | `nodes/<id>.yaml`                                   |
| `issue`             | `issues/<KEY>/issue.yaml`                           |
| `session`           | `sessions/<id>/session.yaml`                        |
| `decision`          | concept node with `type: decision`                  |
| `comment`           | `issues/<KEY>/comments/<n>.yaml`                    |
| `pull-request`      | session/issue artifacts referencing a PR            |
| `tripwire-instance` | tripwire fire records (forward-compat)              |

`GraphNode.kind` is intentionally a loose `str` so existing on-disk
YAML using `kind="issue"` / `kind="node"` keeps loading. The
`NodeKind` enum is the canonical name set for new code.

### Edge kinds (`EdgeKind`)

The 7 canonical edge kinds:

| Kind                | Direction                              | Inverse name        |
| ------------------- | -------------------------------------- | ------------------- |
| `refs`              | bidirectional                          | `refs`              |
| `depends_on`        | source depends on target               | `blocks`            |
| `implements`        | source implements target               | `implemented-by`    |
| `produced-by`       | source was produced by target          | `produces`          |
| `supersedes`        | source supersedes target               | `superseded-by`     |
| `addressed-by`      | source is addressed by target          | `addresses`         |
| `tripwire-fired-on` | source (tripwire) fired on target      | `fired-tripwires`   |

Inverses are computed at read time by
`core.graph.edges.inverse_kind()` — they are never stored on disk.
This matches the existing `blocks` convention (which has been
inverse-computed since v0.6).

### Per-edge fields

`GraphEdge` gains two optional fields:

- `via_artifact: str | None` — the artifact (file, comment,
  decision) that produced the edge. Used by the UI to deep-link
  back to the prose that introduced the edge.
- `line: int | None` — line number for body refs.

Existing `source_file` is retained; new edges should populate both
`source_file` and `via_artifact` (typically the same value).

### Legacy → canonical mapping

`core.graph.index.canonical_kind()` translates legacy edge type
strings stored in `graph/index.yaml` to the canonical kind:

| Legacy        | Canonical       |
| ------------- | --------------- |
| `references`  | `refs`          |
| `related`     | `refs`          |
| `blocked_by`  | `depends_on`    |
| `implements`  | `implements`    |
| (others)      | unchanged       |

Unknown strings pass through unchanged (forward-compat).

## Module layout

```
src/tripwire/core/graph/
├── __init__.py         re-exports submodules
├── cache.py            on-disk cache (file IO, fingerprinting, locking)
├── concept.py          legacy concept-graph view (delegates to cache)
├── dependency.py       legacy dependency-graph view (delegates to cache)
├── edges.py            edge-kind directionality + inverse mapping
├── index.py            UnifiedIndex facade — canonical query API
├── refs.py             [[id]] / [[id@vN]] reference parser
└── version_pin.py      pin-syntax helpers
```

The flat modules `core/graph_cache.py`, `core/concept_graph.py`,
`core/dependency_graph.py`, `core/reference_parser.py` are retained
as backward-compat shims that re-export from the new package paths.

## Backward compatibility

- Existing `graph/index.yaml` files load cleanly (no new required
  fields; `via_artifact` and `line` default to None).
- Existing imports (`from tripwire.core.graph_cache import …`)
  keep working via shim modules at the old paths.
- `GraphNode.kind` accepts both legacy strings (`"issue"`,
  `"node"`) and the canonical `NodeKind` values.
- Legacy edge type strings (`"references"`, `"blocked_by"`, etc.)
  continue to be written by the cache; the unified facade
  translates them to canonical kinds at query time.

A future `_schema_version` field is intentionally deferred to
v1.0 (TW1-4); v0.9's compatibility surface is structural.

## CLI surface

`tripwire graph` is now a Click group:

- `tripwire graph render` — existing rendering (mermaid / dot / json
  with `--type deps|concept` and `--upstream/--downstream` filters).
  The bare `tripwire graph` form is retained as an alias.
- `tripwire graph query upstream <id>` — cross-type traversal
  upward (things `<id>` points at).
- `tripwire graph query downstream <id>` — cross-type traversal
  downward (things that point at `<id>`).
- `--kind refs,depends_on` filters by canonical edge kind.
- `--type issue,session` filters by canonical node kind.
- `--distance N` for transitive closure.

## Versioning + pin syntax

Every Pydantic frontmatter model (`Issue`, `AgentSession`,
`Comment`, `Project`, `ConceptNode`) gains an integer `version`
field defaulting to 1. The reference parser accepts an optional
`@vN` suffix:

- `[[id]]` — latest version
- `[[id@v3]]` — pinned to version 3

`core.graph.version_pin.parse_pin()` returns the bare id and the
optional version. `core.graph.refs.extract_references()` continues
to return bare ids; the new `extract_references_with_pins()` returns
tuples for callers that need the version annotation.

## Drift report

`tripwire drift report` produces a single coherence score (0-100)
computed from weighted drift signals:

- Stale pins (heavy)
- Stale concepts (medium)
- Unresolved refs (heavy)
- Workflow-drift events (medium, from KUI-123 events log)

The breakdown is rendered alongside the headline number. Score
weighting is calibrated against the v0 PT corpus and lives at
`core.drift.WEIGHTS`.

## Out of scope

- LLM-based bump suggestion (deferred to v1.0 / TW1-6)
- Concrete deviation tripwires (`v09-entity-graph-consumers`)
- Drift Report UI (KUI-157, same)
- Schema versioning / migrations (deferred to v1.0 / TW1-4, TW1-5)
