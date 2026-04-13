# Concept Graph

The concept graph is the mechanism that keeps issues, code, contracts,
and decisions coherent as a project evolves. It's the single most
important design element in this system — more important than the issue
schema or the validation gate.

## The problem it solves

Without a concept graph, three things drift independently:

1. The issue text (written once, stale forever)
2. The actual code (changes via PRs)
3. The doc or contract the issue referenced (changes separately)

Nobody notices until a downstream agent picks up a later issue and
builds against stale information. Agents compound the damage because
they can't tell which source is authoritative. **Drift is a tax on
every future agent invocation.**

## The solution

A **concept node** is a named, versioned pointer to a concrete artifact
in the codebase. Instead of prose like "the auth endpoint in the
backend", issues reference `[[auth-token-endpoint]]` — a stable
identifier that resolves to a specific file, line range, and content
hash.

## When to create a node

**When in doubt, create the node.** The cost of a node is 30 seconds
of writing a YAML file. The cost of a missing node is undetected
drift across every issue that mentions the concept in prose.

Create a node when ANY of these are true:
- The concept appears in 2+ issues
- The concept crosses a repo boundary
- The concept is a contract or interface between components
- The concept is a decision that constrains downstream work
- The concept is a schema, data model, or API endpoint that other
  things validate against

**Granularity:** A node should be specific enough to have a single
owner (one file, one schema, one endpoint) but general enough to be
meaningfully referenced. If you'd link to it in a design doc, it
should be a node. If a node covers an entire repo, it's too broad —
break it into the concepts within the repo that other things
actually reference.

Good candidates:
- API endpoints (one node per endpoint or endpoint group)
- Data schemas (Firestore collections, config schemas, event types)
- Contracts between systems (SSE event model, approval flow)
- Decisions that constrain work (storage choice, auth approach)
- Shared libraries or SDKs (but subdivide: the SDK is one node, the
  client class within it that others import is another)
- Infrastructure resources consumed by application code

Bad candidates (keep as prose):
- A single helper function only one issue mentions
- Local variables or implementation details
- Things internal to a single file that nothing else references

## Granularity benchmarks

**Target ratio:** ~0.7-0.9x the number of concrete issues. An
8,000-line planning corpus with 60 concrete issues should produce
40-55 nodes. If your node count is below 0.6x your concrete issue
count, you are likely grouping concepts that should be separate
nodes.

**Splitting signals:**
- A node whose description uses "and" to join two distinct concepts
  should be split (e.g., "auth endpoint and rate limiter" → two
  nodes).
- A node referenced by issues that don't otherwise overlap — those
  issues reference different aspects of the grouped concept.

**Merging signals:**
- A node referenced by only 1 issue after the second-pass check is
  a candidate for merging, unless it's genuinely unique (e.g., a
  single Terraform resource).

## Reference syntax

`[[node-id]]` in any Markdown body (issue, node description, comment)
parses as a reference. The reference parser:

- Matches lowercase, letter-first, hyphenated slugs
- Skips fenced code blocks (`` ``` `` and `~~~`)
- Deduplicates within a file but preserves document order

Examples:
- ✓ `Uses the [[user-model]] for lookups.`
- ✓ `See [[dec-003-session-tokens]] for the rationale.`
- ✗ `[[UserModel]]` — uppercase not allowed
- ✗ `[[user_model]]` — underscores not allowed
- ✗ `Inside a ``` code block ``` [[ref]]` — skipped by the parser

## The graph cache

`graph/index.yaml` is a committed cache of the concept graph built from
scanning every issue and node file. Its purpose is to make graph reads
O(1) without rescanning everything.

The validator rebuilds the cache as a side effect. You never edit it
by hand — delete it and run `validate` if you think it's corrupt.

## Freshness

Every active node with a `source` has a `content_hash`. During
validation, the freshness checker fetches the current content at the
node's source path and compares hashes. Different hash → stale node.

When you update code that a node points at, you must rehash the node:

1. Read the current content (respecting `source.lines` if set)
2. Compute `sha256:<hex>`
3. Update `source.content_hash` and `updated_at` in the node file

Leave `content_hash: null` if you don't know — the validator will flag
it as stale and the next agent working there can rehash.

## Edge types

Edges are derived from the data, never stored as separate files:

| Edge | Source | How |
|---|---|---|
| Issue → Node | issue body | `[[node-id]]` in the Markdown |
| Issue → Issue | issue frontmatter | `blocked_by: [OTHER-1]` |
| Issue → Requirement | issue frontmatter | `implements: [REQ-001]` |
| Node → Node | node frontmatter | `related: [other-node]` (bi-directional) |
| Node → Source | node frontmatter | `source: {repo, path, lines, content_hash}` |

## Bi-directional `related`

If `node-a.related` contains `node-b`, then `node-b.related` must
contain `node-a`. The validator warns on one-sided refs and `--fix`
auto-adds the missing side. Write both sides yourself — it's clearer.

## Commands

- `keel refs list <issue-key>` — see an issue's references
- `keel refs reverse <node-id>` — see what references a node
- `keel refs check` — full scan for dangling/orphan/stale refs
- `keel node check [node-id]` — freshness check
- `keel graph --type concept` — render the full graph

## See also

- `examples/node-*.yaml` — one example per node type
- `SCHEMA_NODES.md` — the node file schema
- `REFERENCES.md` — `[[node-id]]` syntax and bi-directional rules
- `VALIDATION.md` — the reference integrity checks
