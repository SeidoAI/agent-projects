# Schema: Concept Nodes

Concept nodes live at `graph/nodes/<id>.yaml`. They are named, versioned
pointers to concrete artifacts in the codebase — the core mechanism for
coherence in an agent-driven project. The canonical examples are under
`examples/node-*.yaml` — **trust the examples over this doc**.

## Frontmatter fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `uuid` | UUID4 | yes | Canonical identity. Agent-generated. |
| `id` | string | yes | Lowercase slug, letter-first, hyphenated. Must match filename. |
| `type` | string | yes | Must be in `enums/node_type.yaml`. |
| `name` | string | yes | Human-readable name. |
| `description` | string | no | One-line summary. |
| `source` | NodeSource | no | Where the concept lives in code. Optional for `planned` nodes. |
| `related` | list[string] | no | Other node ids this connects to. **Bi-directional**. |
| `tags` | list[string] | no | Free-form tags. |
| `status` | string | yes | Must be in `enums/node_status.yaml`. Default `active`. |
| `created_at` | ISO datetime | yes | |
| `updated_at` | ISO datetime | yes | |
| `created_by` | string | no | |

## NodeSource fields

```yaml
source:
  repo: SeidoAI/web-app-backend    # GitHub slug
  path: src/api/auth.py            # path within the repo
  lines: [45, 82]                  # optional 1-indexed inclusive line range
  branch: test                     # optional; defaults to the repo's default
  content_hash: "sha256:..."       # SHA-256 of the current content
```

- `source` is **optional** — `planned` nodes have no source yet,
  decisions may point to docs, configs may just document an env var name.
- `source.lines` is optional — omit for whole-file references.
- `source.content_hash` is what the freshness check compares against.

## Node types (`enums/node_type.yaml`)

- `endpoint` — a route handler / API endpoint
- `model` — a data class, schema, or ORM model
- `config` — an environment variable, feature flag, or configuration value
- `tf_output` — a Terraform output that other repos consume
- `contract` — an API contract document or OpenAPI section
- `decision` — an architectural or product decision (DEC-xxx)
- `requirement` — a requirement (REQ-xxx)
- `service` — a running service or deployment
- `schema` — a database schema or migration
- `custom` — anything else

## When to create a node

The rule is simple: **create a node when a concept is referenced by
multiple issues OR crosses a repo boundary**. One-off mentions stay as
inline prose. A new endpoint that only one issue cares about stays as
prose. A new endpoint that downstream issues need to call gets a node.

Full discussion: `CONCEPT_GRAPH.md`.

## Body

Optional Markdown description. Useful for:

- Response shapes (for endpoints and contracts)
- Migration notes (for schemas)
- Rationale and consequences (for decisions)
- Access patterns (for configs)

The body is free-form but can contain `[[references]]` to other nodes.
The validator parses them and they count toward the reference integrity
check.

## File path

`<project>/graph/nodes/<id>.yaml`. The filename (minus `.yaml`) must
exactly match the `id` field.

## Bi-directional `related`

If `node-a.related` contains `node-b`, then `node-b.related` must
contain `node-a`. The validator warns on asymmetry and `--fix` auto-
adds the missing side. You can just write both sides yourself — it's
clearer.

## Content hashing

When you create a node with a `source`, compute the SHA-256 of the
current content at that path+lines and put it in `source.content_hash`
as `sha256:<hex>`. The freshness check will compare this against the
live content during validation.

Cannot compute a hash? Leave `content_hash: null` — the validator will
treat the node as stale on first check, and the PM agent or a coding
agent can rehash it later.

## See also

- `examples/node-endpoint.yaml` — endpoint with full source
- `examples/node-model.yaml` — model pointing to a class
- `examples/node-decision.yaml` — decision pointing to a markdown doc
- `examples/node-config.yaml` — config for an env var
- `examples/node-contract.yaml` — contract pointing to an OpenAPI section
- `CONCEPT_GRAPH.md` — the when-to-create-a-node rule
- `REFERENCES.md` — `[[node-id]]` syntax and bi-directional rules
