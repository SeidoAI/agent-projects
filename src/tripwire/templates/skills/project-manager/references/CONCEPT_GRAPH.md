# Concept Graph

Keeps issues, code, contracts, and decisions coherent as the project
evolves. The most important design element in this system — more so
than the issue schema or the validation gate.

## What it solves

Without it, three things drift independently: issue text (written once,
stale forever), code (changes via PRs), and the doc or contract the
issue referenced. Downstream agents pick up a later issue and build
against stale info. **Drift is a tax on every future agent invocation.**

A **concept node** is a named, versioned pointer to a concrete
artifact. Issues reference `[[auth-token-endpoint]]` — a stable id
resolving to a file, optional line range, and content hash — instead
of prose like "the auth endpoint in the backend".

## When to create a node

**When in doubt, create it.** Node = 30s of YAML; missing node =
undetected drift everywhere the concept appears in prose.

Create when ANY apply:
- Appears in 2+ issues
- Crosses a repo boundary
- Is a contract or interface between components
- Is a decision that constrains downstream work
- Is a schema, model, or endpoint that other things validate against

**Granularity:** specific enough to have one owner (file, schema,
endpoint), general enough to be meaningfully referenced. If you'd link
to it in a design doc, it's a node. Whole-repo nodes are too broad —
split into the concepts within the repo that other things reference.

Good (code-anchored): API endpoints, data schemas (collections, config
schemas, event types), inter-system contracts (SSE event model, approval
flow), constraint decisions, shared libraries (subdivide: SDK + the client
class others import), infra resources consumed by app code.

Good (conceptual): principles guiding many decisions, practices codifying
recurring work (kebab-case slugs, every session writes verified.md),
glossary terms with project-specific meaning, metrics driving process
review, personas (PM agent, coding agent, reviewer), invariants the
system must preserve, anti-patterns the team has ruled out.

Bad (keep as prose): single helper functions, local variables,
page-specific UX details, things internal to one file that nothing else
references.

## Granularity benchmarks

Target node count: ~0.7-0.9x concrete issues. 60 issues → 40-55 nodes.
Below 0.6x → likely grouping concepts that should be separate.

Splitting signals: descriptions using "and" to join distinct concepts
("auth endpoint and rate limiter" → two), or a node referenced by
non-overlapping issues (different aspects of the grouped concept).

Merging signal: only 1 referrer after the second-pass check, unless
it's genuinely unique (a single Terraform resource).

## Reference syntax

`[[node-id]]` in any Markdown body. Parser matches lowercase,
letter-first, hyphenated slugs, skips fenced code blocks (` ``` ` and
`~~~`), and deduplicates within a file while preserving order.

- ✓ `[[user-model]]`, `[[dec-003-session-tokens]]`
- ✗ `[[UserModel]]` (uppercase), `[[user_model]]` (underscore)

## Graph cache

`nodes/tripwire-graph-index.yaml` is a committed cache for O(1) reads. Validator
rebuilds it as a side effect. Don't hand-edit — delete and re-validate
if corrupt.

## Freshness

Every active node with a `source` has a `content_hash`. Validate
fetches the current content and compares. Mismatch → stale.

When you change code at a node's source: read the content (respecting
`source.lines` if set), compute `sha256:<hex>`, update
`source.content_hash` and `updated_at`. If you don't know, leave
`content_hash: null` — validator flags it stale and the next agent
rehashes.

## Edge types

Derived from data, never stored as separate files:

| Edge | Source | How |
|---|---|---|
| Issue → Node | issue body | `[[node-id]]` |
| Issue → Issue | frontmatter | `blocked_by: [OTHER-1]` |
| Issue → Requirement | frontmatter | `implements: [REQ-001]` |
| Node → Node | frontmatter | `related: [other-node]` (bi-directional) |
| Node → Source | frontmatter | `source: {repo, path, lines, content_hash}` |

`related` is bi-directional: if `a.related ⊇ {b}` then
`b.related ⊇ {a}`. Validator warns on one-sided refs; `--fix`
auto-adds the missing side. Write both yourself — it's clearer.

## Commands

- `tripwire refs list <issue-key>` — issue's references
- `tripwire refs reverse <node-id>` — what references a node
- `tripwire refs check` — full dangling/orphan/stale scan
- `tripwire node check [node-id]` — freshness check
- `tripwire graph --type concept` — render the graph

## See also

- `examples/node-*.yaml` — one example per node type
- `SCHEMA_NODES.md` — node schema
- `REFERENCES.md` — syntax and bi-directional rules
- `VALIDATION.md` — reference-integrity checks
