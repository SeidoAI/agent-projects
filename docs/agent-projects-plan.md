# Plan v2: `agent-project` — Git-Native Agent Project Management Framework

## Context

We're replacing Linear + Notion with a single git-native project management system designed for AI agent collaboration. The current system (`linear-project-manager` skill in `ide-config`) is comprehensive but suffers from:
- **Slow feedback loops**: human-in-the-loop when not needed
- **Alignment drift**: three canonical sources (Notion, Linear, code) that fall out of sync
- **Agent navigation problems**: disparate docs are hard for agents to find and use
- **No automated status transitions**: status changes require manual intervention

**Phase 1 (this plan)** focuses on the **data layer** — an installable Python package that manages issues, concept graph, dependencies, status, and agent sessions as files in a git repo. Automation (GitHub Actions, agent triggering) and UI come later.

**Target directory**: `/Users/maia/Code/seido/projects/agent-projects/`

---

## Decisions

- **Package name**: `agent-project` (generic, not Seido-branded)
- **CLI command**: `agent-project`
- **File format**: YAML frontmatter + Markdown body (`.yaml` extension, `---` separator)
- **Status flow**: Full 9-status flow as default, configurable per project
- **Build system**: `hatchling` (matches existing ecosystem)
- **CLI framework**: `click` (mature, explicit, no magic)
- **Linting**: `ruff` (line-length 88, matching existing conventions)
- **Concept graph**: File-based nodes in `graph/nodes/`, content-hash staleness detection
- **Repo resolution**: Local clone preferred, GitHub API fallback

---

## The Coherence Problem and the Concept Graph

### Why this matters

The single biggest problem in agent-driven development is **coherence drift**. When an issue says "implement the `/auth/token` endpoint per the API contract," three things can drift independently:

1. The issue description (static once written)
2. The actual code (changes via PRs)
3. The contract document (changes separately)

Nobody notices until an agent picks up a downstream ticket and builds against stale information. This creates cascading failures: wrong API contracts, mismatched schemas, broken integrations — all because the references in tickets are just prose, not live links.

### The solution: concept nodes as stable references

A **concept node** is a named, versioned pointer to a concrete artifact in the codebase. Instead of prose like "the auth endpoint in the backend," issues reference `[[auth-token-endpoint]]` — a stable identifier that resolves to a specific file, line range, and content hash.

This gives us three things:
1. **Indirection**: When code moves, update one node file instead of N issues
2. **Staleness detection**: Content hashing tells us when referenced code has changed
3. **Cross-repo linking**: A terraform output in one repo can be referenced by a backend issue in another

### Explicit nodes vs implicit references — when to use each

Not everything needs a node. The rule is simple:

**Create a node when a concept is referenced by multiple issues or across repos.** Think of nodes as named bookmarks into the codebase. A one-off file mention in a single issue stays as inline prose.

The practical workflow: when a coding agent implements something that other issues will need to reference (a new endpoint, a new model, a terraform output), the PM agent creates a node for it during the update workflow. This is already part of the existing linear-project-manager update workflow — we're just giving it a concrete mechanism.

### Why content hashing beats commit-based checking

We store a SHA-256 hash of the content at the referenced location (specific file + line range). On validation:

1. Fetch current content of the file at those lines (locally or via GitHub API)
2. Hash it
3. Compare to stored `content_hash`
4. **Different hash = content changed = reference potentially stale**

Why this is better than tracking commits:
- **Precise**: A commit might change line 90 but not lines 45-82. No false positive.
- **Works without git history**: Just needs the file content. Works via GitHub API for remote repos.
- **Works across repos**: No need to track which commits touched what — just compare hashes.
- **Detects meaningful changes**: A commit that only changed whitespace elsewhere doesn't trigger a false alarm.

### The PM agent as graph maintainer

The concept graph is not maintained by humans. It's maintained by agents as part of their existing workflows:

**Coding agent** (during implementation):
- Creates nodes for new artifacts it built (endpoints, models, configs)
- References existing nodes in its PR description and completion comment via `[[node-id]]`
- Updates existing nodes if it modified referenced code (rehash)

**PM agent** (during update workflow — already defined in the current skill):
- Runs `agent-project node check` to detect stale nodes after an issue completes
- Updates node `source` fields when code has moved
- Rehashes content after updates
- Identifies downstream issues that reference changed nodes
- Proposes issue updates as PRs when staleness is detected

**PM agent** (during creation/triage):
- When writing new issues, references existing nodes instead of prose descriptions
- Creates placeholder nodes (status: `planned`) for things that don't exist yet but will

This means graph maintenance is **not an additional task** — it's woven into the workflows agents already perform.

---

## Package Structure

```
agent-projects/                          # /Users/maia/Code/seido/projects/agent-projects/
├── pyproject.toml
├── Makefile
├── src/
│   └── agent_project/
│       ├── __init__.py
│       ├── models/                      # Pydantic v2 data models
│       │   ├── __init__.py
│       │   ├── enums.py                 # IssueStatus, Priority, Executor, Verifier, NodeType, etc.
│       │   ├── issue.py                 # Issue model
│       │   ├── project.py               # ProjectConfig model
│       │   ├── comment.py               # Comment model
│       │   ├── node.py                  # ConceptNode model (concept graph)
│       │   ├── session.py               # AgentSession, Wave, AgentDivisionPlan
│       │   └── graph.py                 # DependencyGraphResult, FullGraphResult (computed)
│       │
│       ├── core/                        # Business logic (stateless)
│       │   ├── __init__.py
│       │   ├── store.py                 # Read/write issues, project config, comments from disk
│       │   ├── node_store.py            # Read/write concept nodes, index generation
│       │   ├── parser.py                # YAML frontmatter + Markdown body parsing
│       │   ├── reference_parser.py      # Extract [[node-id]] references from Markdown bodies
│       │   ├── freshness.py             # Content hashing + staleness detection (local + GitHub API)
│       │   ├── validator.py             # Issue quality validation (from validate_agent_issue.py)
│       │   ├── dependency_graph.py      # Issue dependency graph (from dependency_graph.py)
│       │   ├── concept_graph.py         # Full graph: issues + nodes + edges (unified view)
│       │   ├── status.py                # Status transitions, dashboard aggregation
│       │   └── id_generator.py          # Auto-increment <PREFIX>-<N> keys
│       │
│       ├── cli/                         # Click CLI
│       │   ├── __init__.py
│       │   ├── main.py                  # Root group + global options
│       │   ├── init.py                  # `agent-project init`
│       │   ├── issue.py                 # `agent-project issue {create,list,show,update,validate}`
│       │   ├── node.py                  # `agent-project node {create,list,show,check,update}`
│       │   ├── refs.py                  # `agent-project refs {list,reverse,check}`
│       │   ├── status.py                # `agent-project status`
│       │   ├── graph.py                 # `agent-project graph` (dependency + concept)
│       │   └── session.py               # `agent-project session {create,list}`
│       │
│       ├── templates/                   # Jinja2 templates for `init`
│       │   ├── __init__.py              # Template loader
│       │   ├── project/                 # Project scaffold files
│       │   │   ├── project.yaml.j2
│       │   │   ├── CLAUDE.md.j2
│       │   │   └── gitignore.j2
│       │   ├── skills/                  # PM agent skill (adapted from linear-project-manager)
│       │   │   ├── SKILL.md.j2
│       │   │   └── references/          # Workflow docs (ported from current skill)
│       │   │       ├── WORKFLOWS_CREATION.md
│       │   │       ├── WORKFLOWS_REVIEW.md
│       │   │       ├── WORKFLOWS_UPDATE.md
│       │   │       ├── WORKFLOWS_TRIAGE.md
│       │   │       ├── WORKFLOWS_VERIFICATION.md
│       │   │       ├── WORKFLOWS_AGENT_DIVISION.md
│       │   │       └── POLICIES.md
│       │   └── issue_templates/         # Template for new issues
│       │       └── default.yaml.j2
│       │
│       └── output/                      # Output formatters
│           ├── __init__.py
│           ├── console.py               # Rich terminal output
│           └── mermaid.py               # Mermaid diagram generation (deps + concept graph)
│
└── tests/
    ├── conftest.py                      # Fixtures: tmp project dirs, sample issues, sample nodes
    ├── unit/
    │   ├── test_models.py
    │   ├── test_parser.py
    │   ├── test_reference_parser.py
    │   ├── test_store.py
    │   ├── test_node_store.py
    │   ├── test_freshness.py
    │   ├── test_validator.py
    │   ├── test_dependency_graph.py
    │   ├── test_concept_graph.py
    │   ├── test_status.py
    │   └── test_id_generator.py
    └── integration/
        ├── test_init.py
        ├── test_issue_lifecycle.py
        └── test_node_lifecycle.py
```

---

## Data Model

### Generated Project Directory (output of `agent-project init`)

```
my-project/
├── project.yaml                    # ProjectConfig
├── CLAUDE.md                       # PM agent entry point → skill
├── .claude/
│   └── skills/
│       └── project-manager/
│           ├── SKILL.md            # Full PM agent operating instructions
│           └── references/         # Workflow docs (progressive disclosure)
├── issues/                         # One file per issue
│   └── .gitkeep
├── graph/
│   └── nodes/                      # One file per concept node
│       └── .gitkeep
├── docs/
│   └── issues/                     # Per-issue artifacts (developer.md, verified.md)
│       └── .gitkeep
├── sessions/                       # Agent session/division plans
│   └── .gitkeep
└── .gitignore
```

### Enums

```python
class IssueStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    REVIEWING = "reviewing"
    TESTING = "testing"
    READY = "ready"
    UPDATING = "updating"
    DONE = "done"
    CANCELED = "canceled"

class Executor(StrEnum):
    AI = "ai"
    HUMAN = "human"
    MIXED = "mixed"

class Verifier(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    NONE = "none"

class Priority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class NodeType(StrEnum):
    ENDPOINT = "endpoint"        # API endpoint
    MODEL = "model"              # Data model / schema / class
    CONFIG = "config"            # Env var, secret, configuration value
    TF_OUTPUT = "tf_output"      # Terraform output (cross-repo infra)
    CONTRACT = "contract"        # API contract / OpenAPI spec section
    DECISION = "decision"        # Architectural decision (DEC-xxx)
    REQUIREMENT = "requirement"  # Requirement (REQ-xxx)
    SERVICE = "service"          # A running service / deployment
    SCHEMA = "schema"            # Database schema / migration
    CUSTOM = "custom"            # User-defined type

class NodeStatus(StrEnum):
    ACTIVE = "active"            # Points to existing, current code
    PLANNED = "planned"          # Will exist after some issue completes
    DEPRECATED = "deprecated"    # Exists but scheduled for removal
    STALE = "stale"              # Content hash mismatch detected
```

### Issue File Format (YAML frontmatter + Markdown body)

```yaml
# issues/PRJ-42.yaml
---
id: PRJ-42
title: Implement user authentication endpoint
status: todo
priority: high
executor: ai
verifier: required
agent: backend-api
labels:
  - domain/backend
  - env/test
parent: PRJ-8
repo: SeidoAI/web-app-backend
base_branch: test
implements:
  - REQ-AUTH-001
  - DEC-003
blocked_by:
  - PRJ-40
blocks:
  - PRJ-45
created_at: "2026-03-26T15:00:00"
updated_at: "2026-03-26T15:00:00"
created_by: pm-agent
---
## Context
The API needs a JWT authentication endpoint for the frontend SPA.
Must consume the [[user-model]] for credential validation and respect
the rate limiting rules in [[dec-007-rate-limiting]].

## Implements
REQ-AUTH-001, DEC-003

## Repo scope
- Repo: SeidoAI/web-app-backend
- Base branch: test
- Primary paths: src/api/auth.py, tests/unit/test_auth.py
- Required config: [[config-firebase-project-id]], [[config-jwt-secret]]

## Requirements
- POST /auth/token accepts email + password, returns JWT
- JWT expires after 1 hour
- Invalid credentials return 401 with standard error model
- Must use the [[user-firestore-schema]] for lookups

## Execution constraints
- Do not make new product/architecture decisions.
- If any ambiguity blocks correct work, stop and ask in the issue comments.

## Acceptance criteria
- [ ] Happy path returns 200 + valid JWT
- [ ] Invalid credentials return 401
- [ ] Expired token returns 403
- [ ] CI passing

## Test plan
```bash
uv run pytest tests/unit/test_auth.py -v
make lint
```

## Dependencies
PRJ-40 (Firestore user model must land first — see [[user-model]])

## Definition of Done
- [ ] Implementation complete
- [ ] Tests added/updated
- [ ] Completion comment added
- [ ] docs/issues/PRJ-42/developer.md added
- [ ] docs/issues/PRJ-42/verified.md added
- [ ] Concept nodes created/updated for new artifacts
```

Note the `[[node-id]]` references throughout the body. These are parsed by the reference parser
and resolved against the concept graph. They serve as live links to code locations that can be
validated for freshness.

### Concept Node File Format

Concept nodes are the core mechanism for coherence. Each node is a named, versioned pointer
to a concrete artifact in the codebase.

```yaml
# graph/nodes/auth-token-endpoint.yaml
---
id: auth-token-endpoint
type: endpoint
name: "POST /auth/token"
description: "JWT authentication endpoint - accepts email + password, returns access token"
source:
  repo: SeidoAI/web-app-backend
  path: src/api/auth.py
  lines: [45, 82]
  branch: test
  content_hash: "sha256:e3b0c44298fc1c149afbf4c8996fb924"
related:
  - user-model
  - dec-003-session-tokens
tags: [auth, api, public]
status: active
created_at: "2026-03-26T15:00:00"
updated_at: "2026-03-26T15:00:00"
created_by: claude
---
JWT authentication endpoint for the frontend SPA. Accepts email + password
credentials, validates against Firestore user collection, returns a signed
JWT with 1-hour expiry.

Response shape:
```json
{ "access_token": "eyJ...", "expires_in": 3600, "token_type": "bearer" }
```
```

**Design decisions for node files:**

- **`id` is a slug, not a UUID.** Slugs are human-readable and meaningful in `[[references]]`.
  `[[auth-token-endpoint]]` is self-documenting; `[[a1b2c3d4]]` is not. Slugs are unique
  within a project (enforced by filename = id).
- **`source` is optional.** A `planned` node doesn't point to code yet. A `decision` node
  might point to a decision document rather than code. A `config` node might just document
  an env var name without pointing to where it's read.
- **`source.lines` is optional.** For whole-file references (a model class that IS the file),
  omit lines and hash the entire file.
- **`related` lists other node IDs.** These are the node-to-node edges. Combined with the
  `[[references]]` in issue bodies (issue-to-node edges) and `blocked_by`/`blocks` in issue
  frontmatter (issue-to-issue edges), the full graph is emergent from the data.
- **The Markdown body** is optional free-form description. Useful for documenting contracts,
  response shapes, migration notes — things that don't live neatly in the code itself.

### Node type examples

**Endpoint node** — points to a route handler:
```yaml
id: auth-token-endpoint
type: endpoint
name: "POST /auth/token"
source:
  repo: SeidoAI/web-app-backend
  path: src/api/auth.py
  lines: [45, 82]
  branch: test
  content_hash: "sha256:..."
```

**Model node** — points to a data class or schema:
```yaml
id: user-model
type: model
name: "User (Firestore)"
source:
  repo: SeidoAI/web-app-backend
  path: src/models/user.py
  lines: [12, 45]
  branch: test
  content_hash: "sha256:..."
```

**Terraform output** — cross-repo infrastructure reference:
```yaml
id: tf-api-url
type: tf_output
name: "api_url (Cloud Run)"
description: "Base URL for the backend API service, consumed by frontend config"
source:
  repo: SeidoAI/web-app-infrastructure
  path: modules/cloud_run/outputs.tf
  lines: [8, 12]
  branch: test
  content_hash: "sha256:..."
related:
  - auth-token-endpoint    # this is the service that serves this URL
```

**Config node** — documents an environment variable:
```yaml
id: config-jwt-secret
type: config
name: "JWT_SECRET"
description: "HMAC signing key for JWT tokens. Must be at least 32 chars."
source:
  repo: SeidoAI/web-app-infrastructure
  path: modules/secrets/main.tf
  lines: [22, 28]
  branch: test
  content_hash: "sha256:..."
tags: [auth, secret]
```

**Contract node** — points to an API contract section:
```yaml
id: contract-auth-token
type: contract
name: "Auth Token Contract"
source:
  repo: SeidoAI/web-app-backend
  path: docs/api-contract.yaml
  lines: [120, 180]
  branch: test
  content_hash: "sha256:..."
related:
  - auth-token-endpoint    # the implementation of this contract
```

**Planned node** — placeholder for something that doesn't exist yet:
```yaml
id: refresh-endpoint
type: endpoint
name: "POST /auth/refresh"
description: "Token refresh endpoint. Will be implemented in PRJ-48."
status: planned
# No source — code doesn't exist yet
```

**Decision node** — points to a decision record (could be in the project repo itself):
```yaml
id: dec-003-session-tokens
type: decision
name: "DEC-003: Session token storage"
description: "JWT in httpOnly cookie, no localStorage. Decided for compliance."
source:
  repo: SeidoAI/web-app-backend    # or wherever the decision doc lives
  path: docs/decisions/DEC-003.md
  content_hash: "sha256:..."
status: active
```

### The edge model — all implicit, no edge files

Edges are not stored as separate files. They are **emergent from the data**:

| Edge type | Source | How it's expressed |
|-----------|--------|-------------------|
| Issue → Node | Issue body | `[[auth-token-endpoint]]` parsed from Markdown |
| Issue → Issue | Issue frontmatter | `blocked_by: [PRJ-40]` and `blocks: [PRJ-45]` |
| Issue → Requirement | Issue frontmatter | `implements: [REQ-AUTH-001]` |
| Node → Node | Node frontmatter | `related: [user-model, dec-003]` |
| Node → Source code | Node frontmatter | `source: {repo, path, lines, content_hash}` |

**Why no edge files:** Edges stored separately from their endpoints create a synchronization problem — the exact problem we're trying to solve. By keeping edges in the entities they belong to, every entity is self-describing. The full graph is reconstructed by scanning all issues and nodes.

The `agent-project graph` command and the `concept_graph.py` module build the complete graph on demand by scanning everything. For larger projects, an auto-generated index speeds up lookups (see below).

### The reference index — auto-generated lookup cache

```yaml
# graph/index.yaml (auto-generated by `agent-project refs rebuild`)
# This file is committed to git for fast lookups but can always be regenerated.

by_name:
  "POST /auth/token": auth-token-endpoint
  "User (Firestore)": user-model
  "JWT_SECRET": config-jwt-secret

by_type:
  endpoint: [auth-token-endpoint, refresh-endpoint]
  model: [user-model, business-model]
  config: [config-jwt-secret, config-firebase-project-id]
  tf_output: [tf-api-url]
  contract: [contract-auth-token]
  decision: [dec-003-session-tokens]

# Reverse references: which issues reference each node
referenced_by:
  auth-token-endpoint: [PRJ-42, PRJ-45, PRJ-51]
  user-model: [PRJ-40, PRJ-42]
  config-jwt-secret: [PRJ-42]

# Staleness status (updated by `agent-project node check`)
stale_nodes: []
last_checked: "2026-03-26T18:00:00"
```

This index is rebuilt by `agent-project refs rebuild`. CLI commands like `agent-project refs reverse <node-id>` read from it for speed. If the index is missing or outdated, commands fall back to full scan.

### ProjectConfig (`project.yaml`)

```yaml
name: seido-mvp
key_prefix: SEI
description: Seido MVP project management
base_branch: test
environments: [test, prod]

# Repository registry — maps GitHub slugs to optional local paths
repos:
  SeidoAI/web-app-backend:
    local: ~/Code/seido/web-app        # optional, for fast local freshness checks
  SeidoAI/web-app-frontend:
    local: ~/Code/seido/web-app
  SeidoAI/web-app-infrastructure:
    local: ~/Code/seido/web-app
  SeidoAI/ml-business-agent:
    local: ~/Code/seido/agents/ml-business-agent

statuses:
  - backlog
  - todo
  - in_progress
  - verifying
  - reviewing
  - testing
  - ready
  - updating
  - done
  - canceled

status_transitions:
  backlog: [todo, canceled]
  todo: [in_progress, backlog, canceled]
  in_progress: [verifying, todo, canceled]
  verifying: [reviewing, in_progress]
  reviewing: [testing, in_progress]
  testing: [ready, reviewing]
  ready: [updating]
  updating: [done]
  done: []
  canceled: [backlog]

label_categories:
  executor: [ai, human, mixed]
  verifier: [required, optional, none]
  domain: []
  agent: []

# Concept graph settings
graph:
  # Node types that are valid in this project (extensible)
  node_types: [endpoint, model, config, tf_output, contract, decision, requirement, service, schema]
  # Whether to auto-rebuild index on node/issue changes
  auto_index: true

next_issue_number: 1
created_at: "2026-03-26T14:00:00"
```

### Comment Model

Comments stored as individual files in `docs/issues/<KEY>/comments/`:

```yaml
# docs/issues/PRJ-42/comments/001-start-2026-03-26.yaml
---
issue_key: PRJ-42
author: claude
type: status_change
created_at: "2026-03-26T15:30:22"
---
Starting work on PRJ-42. Created branch `claude/PRJ-42-auth-endpoint`.

No blockers. PRJ-40 merged yesterday. [[user-model]] is available in test branch.
```

Comments can also contain `[[references]]` — this is how agents document which concepts
they're working with, and it feeds the reference index.

### AgentSession Model

Sessions carry runtime state across container re-engagements. The session YAML is the
persistence anchor — it tracks what the agent has done and why it was re-engaged.

```yaml
# sessions/wave1-agent-a.yaml
---
id: wave1-agent-a
name: "Agent A: Auth + User Model"
agent: backend-coder                  # references agents/backend-coder.yaml
issues: [PRJ-40, PRJ-42]
wave: 1
repo: SeidoAI/web-app-backend
estimated_size: medium-large
blocked_by_sessions: []
key_files:
  - src/auth/
  - src/models/user.py
grouping_rationale: Same repo, tight dependency chain, overlapping files

# Session status lifecycle:
#   planned → active → waiting_for_ci → re_engaged → active → ...
#   ... → waiting_for_review → re_engaged → active → ... → completed
status: waiting_for_ci

# Runtime state — persisted across container restarts
runtime_state:
  claude_session_id: "sess_abc123"    # for claude --resume
  langgraph_thread_id: null           # for langgraph checkpoint resume
  workspace_volume: "vol-wave1-a"     # Docker volume name
  branch: "claude/PRJ-40-auth"
  pr_number: 42

# Re-engagement history — append-only log
engagements:
  - started_at: "2026-03-26T14:00:00"
    trigger: initial_launch
    ended_at: "2026-03-26T16:30:00"
    outcome: pr_opened
  - started_at: "2026-03-26T17:15:00"
    trigger: ci_failure
    context: "Lint failure in src/api/auth.py:45 — ruff E302"
    ended_at: "2026-03-26T17:25:00"
    outcome: fix_pushed
---
```

**SessionStatus enum:**

```python
class SessionStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    WAITING_FOR_CI = "waiting_for_ci"
    WAITING_FOR_REVIEW = "waiting_for_review"
    WAITING_FOR_DEPLOY = "waiting_for_deploy"
    RE_ENGAGED = "re_engaged"
    COMPLETED = "completed"
    FAILED = "failed"

class ReEngagementTrigger(StrEnum):
    INITIAL_LAUNCH = "initial_launch"
    CI_FAILURE = "ci_failure"
    VERIFIER_REJECTION = "verifier_rejection"
    HUMAN_REVIEW_CHANGES = "human_review_changes"
    BUG_FOUND = "bug_found"
    DEPLOY_FAILURE = "deploy_failure"
    STALE_REFERENCE = "stale_reference"
    SCOPE_CHANGE = "scope_change"
    MERGE_CONFLICT = "merge_conflict"
    DEPENDENCY_CONFLICT = "dependency_conflict"
    HUMAN_RESPONSE = "human_response"
    PLAN_APPROVED = "plan_approved"
    PLAN_REJECTED = "plan_rejected"
    MANUAL = "manual"
```

### Message Log Model

Messages are delivered in real-time via HTTP (container → UI backend). But a log is
persisted in the project repo when a session completes, at `sessions/<id>/messages.yaml`.

```python
class MessageEntry(BaseModel):
    id: str
    direction: str                     # "agent_to_human" | "human_to_agent"
    type: str                          # question, plan_approval, progress, stuck, ...
    priority: str                      # blocking | informational
    author: str
    created_at: datetime
    body: str
    response: MessageResponse | None = None

class MessageResponse(BaseModel):
    author: str
    created_at: datetime
    body: str
    decision: str | None = None        # "approved" | "rejected" (for plan_approval)

class MessageLog(BaseModel):
    """Written to sessions/<id>/messages.yaml on session completion."""
    session_id: str
    messages: list[MessageEntry]
```

New session directory structure:
```
sessions/
├── wave1-agent-a.yaml               # session definition + runtime state + engagements
└── wave1-agent-a/
    └── messages.yaml                 # message log (committed on session complete)
```

New CLI command:
```
agent-project session finalize <session-id>
  --messages-file TEXT   Path to messages JSON (from UI backend SQLite export)
  # Writes messages.yaml to session directory and commits to project repo.
  # Called by UI backend when session completes.
```

---

## Core Module Responsibilities

### `core/parser.py` — Frontmatter + Body Parser
- Split file on `---` delimiter: YAML frontmatter → structured fields, Markdown body → `body` field
- Round-trip: serialize model back to frontmatter + body format
- Handle edge cases (no body, no frontmatter, body-only)
- Used by both issues and concept nodes (same file format)

### `core/store.py` — Issue & Project CRUD
- `load_project(dir) -> ProjectConfig`
- `save_project(dir, config)`
- `load_issue(dir, key) -> Issue`
- `save_issue(dir, issue)`
- `list_issues(dir, filters) -> list[Issue]`
- `next_key(dir) -> str` (auto-increment from project.yaml)
- `load_comments(dir, key) -> list[Comment]`
- `save_comment(dir, comment)`

### `core/node_store.py` — Concept Node CRUD + Index
- `load_node(dir, id) -> ConceptNode`
- `save_node(dir, node)` — writes to `graph/nodes/<id>.yaml`
- `list_nodes(dir, type_filter, status_filter) -> list[ConceptNode]`
- `delete_node(dir, id)`
- `rebuild_index(dir)` — scan all issues + nodes, build `graph/index.yaml`
- `load_index(dir) -> GraphIndex`
- `resolve_name(dir, name) -> str | None` — name → node ID lookup

### `core/reference_parser.py` — Extract `[[references]]` from Markdown
- Parse `[[node-id]]` patterns from any Markdown body (issues, comments, nodes)
- Return list of referenced node IDs
- Handle edge cases: broken references, nested brackets, code blocks (don't parse inside code fences)
- Provide `replace_references(body, resolver)` for rendering references with links (for UI phase later)

### `core/freshness.py` — Content Hashing + Staleness Detection

This is the core coherence mechanism. It answers: "has the code that this node points to changed?"

- `hash_content(content: str) -> str` — SHA-256 hash of content string
- `fetch_content(source: NodeSource, project: ProjectConfig) -> str | None`
  - Check if repo has a configured local path in `project.yaml`
  - If local: read file, extract lines if specified
  - If not local: use `gh api repos/{owner}/{repo}/contents/{path}?ref={branch}` via GitHub API
  - Return the content string, or None if file not found
- `check_node_freshness(node: ConceptNode, project: ProjectConfig) -> FreshnessResult`
  - Fetch current content
  - Hash it
  - Compare to `node.source.content_hash`
  - Return: `fresh | stale | source_missing | no_source`
- `check_all_nodes(dir) -> list[FreshnessResult]`
  - Batch check all active nodes with sources
  - Report: fresh count, stale count, missing count, details
- `rehash_node(node: ConceptNode, project: ProjectConfig) -> ConceptNode`
  - Fetch current content, compute new hash, update node

**Why local + GitHub API:**
- Local clone is fast (no network, no rate limits). Use it when available.
- GitHub API is the fallback for repos that aren't cloned locally. The `gh` CLI handles auth.
- `project.yaml` maps repo slugs to local paths. This is optional — if no local path is configured, the system uses the GitHub API.

```python
# core/freshness.py — resolution logic

def fetch_content(source: NodeSource, project: ProjectConfig) -> str | None:
    """Fetch content from local clone or GitHub API."""
    repo_config = project.repos.get(source.repo)
    local_path = repo_config.local if repo_config else None

    if local_path:
        expanded = Path(local_path).expanduser()
        if expanded.exists():
            return _read_local(expanded / source.path, source.lines)

    # Fall back to GitHub API
    return _fetch_github(source.repo, source.path, source.lines, source.branch)


def _read_local(file_path: Path, lines: tuple[int, int] | None) -> str | None:
    """Read content from a local file, optionally extracting a line range."""
    if not file_path.exists():
        return None
    text = file_path.read_text(encoding="utf-8")
    if lines:
        file_lines = text.splitlines()
        start, end = lines[0] - 1, lines[1]  # 1-indexed to 0-indexed
        return "\n".join(file_lines[start:end])
    return text


def _fetch_github(repo: str, path: str, lines: tuple[int, int] | None, branch: str) -> str | None:
    """Fetch file content via GitHub API using `gh` CLI."""
    import subprocess
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/contents/{path}", "-q", ".content", "--jq", ".content"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    # GitHub API returns base64-encoded content
    import base64
    content = base64.b64decode(result.stdout.strip()).decode("utf-8")
    if lines:
        file_lines = content.splitlines()
        start, end = lines[0] - 1, lines[1]
        return "\n".join(file_lines[start:end])
    return content
```

### `core/validator.py` — Issue Quality Checks (ported from `validate_agent_issue.py`)
- Check required Markdown headings in body (Context, Implements, Repo scope, Requirements, Acceptance criteria, Test plan, Dependencies, Definition of Done)
- Check "stop and ask" guidance present
- Validate executor/verifier label consistency
- Validate dependency references exist (issue keys)
- **Validate `[[references]]` resolve to existing nodes**
- **Report stale references (nodes whose content_hash is outdated)**
- Warn on placeholder keys (`ISS-\d+`)
- Return structured `ValidationResult` with errors/warnings/stale_refs
- **Validate session status transitions** (e.g., can't go from `planned` to `completed` directly)
- **Warn on sessions stuck in waiting states** (e.g., `waiting_for_ci` for >1 hour with no CI run)
- **Validate session agent references** (agent ID in session must match an `agents/<id>.yaml` file)

### `core/dependency_graph.py` — Issue Dependency Graph (ported from `dependency_graph.py`)
- Build graph from `list[Issue]` (not raw JSON — cleaner input)
- Cycle detection (existing DFS algorithm)
- Critical path computation (existing longest-path DP)
- Mermaid output (enhanced: color nodes by status)
- Graphviz DOT output
- Return `DependencyGraphResult` model

### `core/concept_graph.py` — Full Unified Graph

This builds the complete graph that includes everything: issues, concept nodes, and all edges.
This is what the UI will visualize later.

- `build_full_graph(dir) -> FullGraphResult`
  - Load all issues
  - Load all concept nodes
  - Extract all `[[references]]` from issue bodies
  - Extract all `blocked_by`/`blocks` edges from issue frontmatter
  - Extract all `related` edges from node frontmatter
  - Extract all `source` edges from nodes to code locations
  - Return unified graph with typed nodes and typed edges
- `to_mermaid(graph, filter) -> str` — Render as Mermaid with node-type coloring
- `orphan_nodes(graph) -> list[str]` — Nodes not referenced by any issue
- `orphan_issues(graph) -> list[str]` — Issues with no node references (potential coherence gap)

### `core/status.py` — Status Transitions & Dashboard
- Validate transitions against `project.yaml` rules
- Aggregate counts by status, executor, priority
- Identify blocked issues, stale issues (issues referencing stale nodes)
- Compute critical path summary

### `core/id_generator.py` — Key Generation
- Read `next_issue_number` from project.yaml
- Generate `<PREFIX>-<N>` (e.g., `SEI-42`)
- Atomically increment counter

---

## CLI Commands

### Issue management

```
agent-project init <name>
  --key-prefix TEXT    Issue key prefix (e.g., SEI, PRJ)
  --base-branch TEXT   Default base branch [default: test]
  --repos TEXT         Comma-separated repo list (GitHub slugs)
  --no-git             Skip git init

agent-project issue create
  --title TEXT         Issue title (required)
  --executor TEXT      ai/human/mixed [default: ai]
  --verifier TEXT      required/optional/none [default: required]
  --priority TEXT      urgent/high/medium/low [default: medium]
  --parent TEXT        Parent epic key
  --repo TEXT          Target repo
  --blocked-by TEXT    Comma-separated blocking issue keys
  --labels TEXT        Comma-separated labels
  --template TEXT      Body template to use [default: default]

agent-project issue list
  --status TEXT        Filter by status(es)
  --executor TEXT      Filter by executor type
  --label TEXT         Filter by label
  --parent TEXT        Filter by parent epic
  --format TEXT        table/json/yaml [default: table]

agent-project issue show <key>
  --format TEXT        rich/json/yaml [default: rich]

agent-project issue update <key>
  --status TEXT        New status (validated against transitions)
  --title TEXT         New title
  --priority TEXT      New priority
  --add-label TEXT     Add label
  --remove-label TEXT  Remove label

agent-project issue validate [key]
  --strict             Treat warnings as errors
  --check-refs         Also check freshness of referenced nodes [default: true]
```

### Concept graph

```
agent-project node create
  --id TEXT            Node slug ID (required, must be unique)
  --type TEXT          Node type: endpoint/model/config/tf_output/contract/decision/... (required)
  --name TEXT          Human-readable name (required)
  --repo TEXT          Source repo (GitHub slug)
  --path TEXT          File path within repo
  --lines TEXT         Line range, e.g. "45-82"
  --branch TEXT        Branch to track [default: project base_branch]
  --related TEXT       Comma-separated related node IDs
  --tags TEXT          Comma-separated tags
  --status TEXT        active/planned/deprecated [default: active]
  # If --repo and --path provided, content is fetched and hashed automatically

agent-project node list
  --type TEXT          Filter by node type
  --status TEXT        Filter by status
  --stale              Only show stale nodes
  --format TEXT        table/json/yaml [default: table]

agent-project node show <id>
  --format TEXT        rich/json/yaml [default: rich]

agent-project node check [id]
  # If id provided: check one node. Otherwise: check all active nodes with sources.
  # Fetches current content (local or GitHub API), hashes, compares.
  # Reports: fresh / stale / source_missing for each node.
  --update             Automatically rehash stale nodes (update content_hash + updated_at)
  --format TEXT        table/json [default: table]

agent-project node update <id>
  --path TEXT          Update source file path (e.g., code moved)
  --lines TEXT         Update line range
  --repo TEXT          Update source repo
  --rehash             Fetch current content and update hash
  --status TEXT        Update status (active/planned/deprecated/stale)
  --add-related TEXT   Add related node IDs
  --remove-related TEXT Remove related node IDs
```

### Reference tracking

```
agent-project refs list <issue-key>
  # Show all [[references]] in this issue and their freshness status

agent-project refs reverse <node-id>
  # Show all issues that reference this node

agent-project refs check
  # Full scan: find all references across all issues, check freshness of all
  # referenced nodes, report stale references and orphan nodes
  --format TEXT        table/json [default: table]

agent-project refs rebuild
  # Rebuild the graph/index.yaml from scratch by scanning all issues + nodes
```

### Status and graphs

```
agent-project status
  --format TEXT        rich/json [default: rich]
  # Now includes: stale reference count, orphan node count

agent-project graph
  --format TEXT        mermaid/dot [default: mermaid]
  --output TEXT        Output file path
  --type TEXT          deps (issue dependencies only) / concept (full graph) [default: deps]
  --status-filter TEXT Only include issues with these statuses

agent-project session create
  --name TEXT          Session name
  --agent TEXT         Agent definition ID (references agents/<id>.yaml)
  --issues TEXT        Comma-separated issue keys
  --wave INT           Wave number

agent-project session list
  --status TEXT        Filter by status (planned, active, waiting_for_ci, etc.)
  --wave INT           Filter by wave number
  --format TEXT        table/json [default: table]

agent-project session show <session-id>
  --format TEXT        rich/json/yaml [default: rich]
  # Shows full session detail including engagement history

agent-project session re-engage <session-id>
  --trigger TEXT       Trigger type: ci_failure, verifier_rejection, human_review_changes,
                       bug_found, deploy_failure, stale_reference, scope_change,
                       merge_conflict, dependency_conflict, manual (required)
  --context TEXT       Freeform context string (error output, review comments, etc.)
  --context-file TEXT  Read context from a file (for long CI output, etc.)
  # Appends a new engagement entry to the session, sets status to re_engaged.
  # Used by GitHub Actions and PM agent to trigger re-engagement.

agent-project session update <session-id>
  --status TEXT        Update status (e.g., waiting_for_ci, completed, failed)
  --branch TEXT        Update branch name
  --pr-number INT      Update PR number
  --claude-session TEXT  Update Claude session ID
  --langgraph-thread TEXT  Update LangGraph thread ID
  --volume TEXT        Update Docker volume name
```

---

## Key Files to Reuse / Port

| Source | Target | Notes |
|--------|--------|-------|
| `ide-config/.../scripts/dependency_graph.py` (258 lines) | `core/dependency_graph.py` | Port cycle detection, critical path, Mermaid/DOT output. Change input from JSON to `list[Issue]` |
| `ide-config/.../scripts/validate_agent_issue.py` (62 lines) | `core/validator.py` | Port required headings check, placeholder detection. Add label validation, dependency validation, reference validation |
| `ide-config/.../assets/templates/linear_issue_body.md` | `templates/issue_templates/default.yaml.j2` | Convert from Linear template to YAML frontmatter + body format. Add `[[reference]]` guidance |
| `ide-config/.../SKILL.md` + references/ | `templates/skills/` | Adapt PM agent skill from Linear-based to git-native. Add concept graph maintenance to update workflow |
| `ide-config/.../assets/policies/` | `templates/skills/references/POLICIES.md` | Bundle policies into single reference doc |
| `ml-business-agent/pyproject.toml` | `pyproject.toml` | Follow same conventions: hatchling, ruff, dependency-groups |

---

## Dependencies

```toml
[project]
name = "agent-project"
version = "0.1.0"
description = "Git-native project management with concept graph for AI agents"
requires-python = ">=3.10,<3.14"
dependencies = [
    "pydantic>=2.0,<3.0",
    "click>=8.1,<9.0",
    "pyyaml>=6.0,<7.0",
    "rich>=13.0,<14.0",
    "jinja2>=3.1,<4.0",
]

[project.scripts]
agent-project = "agent_project.cli.main:cli"

[dependency-groups]
dev = [
    "pytest>=8.0,<9.0",
    "ruff>=0.4.6,<1.0",
    "codespell>=2.2,<3.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_project"]

[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "C", "B", "UP", "RUF"]
ignore = ["E501", "C901", "B006"]

[tool.ruff.lint.isort]
known-first-party = ["agent_project"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.codespell]
skip = "uv.lock,.venv"
```

Note: no `gitpython` dependency. Git operations use `subprocess.run(["git", ...])` for simplicity.
GitHub API access uses `subprocess.run(["gh", ...])`. Both `git` and `gh` are expected to be
available in the environment (reasonable for a developer/agent tool).

---

## Implementation Steps

### Step 1: Package scaffold
- Create `pyproject.toml`, `Makefile`, `src/agent_project/__init__.py`
- Set up ruff, pytest config
- Verify `uv sync` and `uv run pytest` work

### Step 2: Enums and core models
- `models/enums.py` — all StrEnum types (IssueStatus, Priority, Executor, Verifier, NodeType, NodeStatus)
- `models/project.py` — ProjectConfig (including `repos` with local paths, `graph` settings)
- `models/issue.py` — Issue (frontmatter fields + body)
- `models/node.py` — ConceptNode, NodeSource (the concept graph node model)
- `models/comment.py` — Comment
- `models/session.py` — AgentSession, Wave
- `models/graph.py` — DependencyGraphResult, FreshnessResult, FullGraphResult, GraphIndex
- Unit tests for model validation, serialization round-trips

### Step 3: Parser, reference parser, and stores
- `core/parser.py` — YAML frontmatter + Markdown body parser/serializer
- `core/reference_parser.py` — `[[node-id]]` extraction from Markdown bodies
- `core/store.py` — File-based CRUD for issues, project config, comments
- `core/node_store.py` — File-based CRUD for concept nodes, index rebuild
- `core/id_generator.py` — Auto-increment keys
- Unit tests for parsing, reference extraction, store operations, key generation

### Step 4: Freshness, validator, and dependency graph
- `core/freshness.py` — Content hashing, local + GitHub API fetching, staleness detection
- `core/validator.py` — Port from `validate_agent_issue.py`, add reference validation
- `core/dependency_graph.py` — Port from `dependency_graph.py`, accept `list[Issue]`
- `core/concept_graph.py` — Full unified graph builder
- `core/status.py` — Transition validation, dashboard aggregation (including staleness)
- `output/mermaid.py` — Mermaid diagram generation (deps + concept graph)
- Unit tests for hashing, freshness checking, validation, graph analysis

### Step 5: CLI — init command
- `cli/main.py` — Click group, global `--project-dir` option
- `cli/init.py` — `agent-project init` generates full project scaffold (including `graph/nodes/`)
- `templates/` — All Jinja2 templates and static files for init
- Port and adapt SKILL.md + workflow references from linear-project-manager (add graph maintenance)
- Integration test: init creates valid project, git repo works

### Step 6: CLI — issue commands
- `cli/issue.py` — create, list, show, update, validate
- `output/console.py` — Rich tables, detail views (show `[[references]]` with freshness indicators)
- Integration test: full issue lifecycle (create → update → validate → list)

### Step 7: CLI — node and refs commands
- `cli/node.py` — create, list, show, check, update
- `cli/refs.py` — list, reverse, check, rebuild
- Integration test: node lifecycle (create → reference in issue → check freshness → update)

### Step 8: CLI — status, graph, session commands
- `cli/status.py` — Dashboard with status breakdown, blocked issues, stale refs, critical path
- `cli/graph.py` — Dependency graph + concept graph output
- `cli/session.py` — Agent session CRUD
- Integration tests

### Step 9: Polish
- Error messages, help text, edge cases
- Ensure `pip install .` and `agent-project --help` work
- Ensure `pip install git+https://github.com/...` works

---

## Verification

1. **Unit tests**: `uv run pytest tests/unit/ -v` — all model validation, parsing, store, graph, validator, freshness tests pass
2. **Integration tests**: `uv run pytest tests/integration/ -v` — init flow, issue lifecycle, node lifecycle
3. **Manual smoke test**:
   ```bash
   cd /tmp && agent-project init test-project --key-prefix TST
   cd test-project

   # Issue CRUD
   agent-project issue create --title "First issue" --executor ai --priority high
   agent-project issue create --title "Second issue" --blocked-by TST-1
   agent-project issue list
   agent-project issue validate
   agent-project issue update TST-1 --status in_progress

   # Concept graph
   agent-project node create --id auth-endpoint --type endpoint --name "POST /auth/token" \
     --repo SeidoAI/web-app-backend --path src/api/auth.py --lines "45-82"
   agent-project node list
   agent-project node show auth-endpoint
   agent-project node check          # checks freshness of all nodes

   # References (after adding [[auth-endpoint]] to an issue body)
   agent-project refs list TST-1
   agent-project refs reverse auth-endpoint
   agent-project refs check          # full staleness scan

   # Dashboard and graph
   agent-project status
   agent-project graph --type deps --format mermaid
   agent-project graph --type concept --format mermaid
   ```
4. **Lint**: `uv run ruff check src/ tests/`
5. **Package install**: `pip install .` from the repo root, then `agent-project --help` works
