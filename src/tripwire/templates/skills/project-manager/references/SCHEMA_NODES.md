# Schema: Concept Nodes

Concept nodes live at `nodes/<id>.yaml`. They are named, versioned
pointers to concrete artifacts in the codebase — the core mechanism for
coherence in an agent-driven project. The canonical examples are under
`examples/node-*.yaml` — **trust the examples over this doc**.

## Frontmatter fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `uuid` | UUID4 | yes | Canonical identity. Agent-generated. |
| `id` | string | yes | Lowercase slug, letter-first, hyphenated. Must match filename. |
| `type` | string | yes | Must be in `enums/node_type.yaml`. |
| `name` | string | yes | Short label for the concept graph (3–5 words, ≤40 chars). See **Naming the node** below. |
| `description` | string | no | One-line summary. |
| `source` | NodeSource | no | Where the concept lives in code. Optional for `planned` nodes. |
| `related` | list[string] | no | Other node ids this connects to. **Bi-directional**. |
| `tags` | list[string] | no | Free-form tags. |
| `status` | string | yes | Must be in `enums/node_status.yaml`. Default `active`. |
| `created_at` | ISO datetime | yes | |
| `updated_at` | ISO datetime | yes | |
| `created_by` | string | no | |

## Naming the node (`name:`)

The `name:` field is the **label that renders on the concept graph**.
It must be scannable at a glance — long sentence-style names crowd the
graph and lose meaning at typical zoom.

Rules:

- **3–5 words, ≤40 characters, Title Case, noun phrase.** What you'd
  point at on a whiteboard.
- **No type prefixes** (`DEC:`, `REQ:`, `Use …`, `Drop …`). The node's
  `type` is already a field — render it as a badge, don't repeat it
  in the label.
- **Concrete artifact, not its rationale.** The name says *what the
  node is*; the rationale lives in the body or `description`.
- **No conjunctions joining two concepts** (`+`, `;`, "and"). If
  you're tempted, the node is two nodes.

Use `description:` for the one-line tagline that hover-previews can
show when more context is needed.

| Type | ✓ Good | ✗ Avoid |
|---|---|---|
| decision | `Cream paper theme` | `DEC: cream paper + ink + rule canonical; dark mode fast-follow` |
| decision | `Hand-rolled SVG graph` | `DEC: drop @xyflow/react in favour of hand-rolled SVG` |
| service | `FastAPI backend` | `Use FastAPI for the tripwire.ui backend` |
| endpoint | `POST /auth/token` | `Auth token issuance endpoint` |
| config | `JWT_SECRET` | `JWT signing secret env var` |

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

**Code-anchored types** (point at a concrete artifact in a repo):

- `endpoint` — a route handler / API endpoint
- `model` — a data class, schema, or ORM model
- `config` — an environment variable, feature flag, or configuration value
- `tf_output` — a Terraform output that other repos consume
- `contract` — an API contract document or OpenAPI section
- `service` — a running service or deployment
- `schema` — a database schema or migration

**Conceptual types** (capture project knowledge that may or may not have a single source artifact):

- `decision` — a one-time architectural or product choice ("we chose A over B"); use when the artifact is the *choice*, not the lens behind it
- `requirement` — a requirement (REQ-xxx) the project must satisfy
- `principle` — a lens decisions are made through; could spawn many decisions ("we always prefer X")
- `practice` — a codified recurring rule for how work gets done; checkable
- `glossary` — a definition of project-specific vocabulary
- `metric` — a measurable signal with a unit or count
- `persona` — an actor (agent or human) with a role
- `invariant` — a rule that must always hold; violations are bugs
- `anti_pattern` — a pattern explicitly ruled out, with rationale

**Escape hatch:**

- `custom` — anything else; use sparingly, prefer the typed alternatives

### Choosing between adjacent types

| If the node is… | Use |
|---|---|
| "We chose A over B" (one-time) | `decision` |
| "We always prefer A through any choice" (lens) | `principle` |
| "How we do X each time" (recurring) | `practice` |
| "A pattern we never use, with reasons" | `anti_pattern` |
| "A defined term in our vocabulary" | `glossary` |
| "A rule that *must* hold; violation = bug" | `invariant` |
| "A measurable signal" | `metric` |
| "An actor / role" | `persona` |

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

`<project>/nodes/<id>.yaml`. The filename (minus `.yaml`) must
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
- `examples/node-principle.yaml` — principle as a design lens
- `examples/node-practice.yaml` — codified recurring rule
- `examples/node-glossary.yaml` — vocabulary definition
- `examples/node-metric.yaml` — measurable signal
- `examples/node-persona.yaml` — actor / role
- `examples/node-invariant.yaml` — must-always-hold rule
- `examples/node-anti-pattern.yaml` — explicitly ruled-out pattern
- `CONCEPT_GRAPH.md` — the when-to-create-a-node rule
- `REFERENCES.md` — `[[node-id]]` syntax and bi-directional rules
