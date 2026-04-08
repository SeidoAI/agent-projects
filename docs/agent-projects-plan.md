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

## How agent-project is used

`agent-project` is not primarily a tool for humans typing CLI commands. Its primary user is Claude Code (or a similar agent) loaded with the `project-manager` skill. Humans interact with the system *through* the agent, not directly. This shapes every other decision in the v0 design.

The first concrete test case is `project-kb-pivot/raw_planning/*.md` — a directory of unstructured planning documents that an agent must transform into a fully scoped project: issues, concept nodes, sessions, decisions, contracts. Until that pipeline works end-to-end, the v0 surface is not done.

**Implications**:

- **The PM skill is the most important artifact in the system.** More than the CLI, more than the templates, more than the validator. The skill is what tells the agent how to think about a project, what to read first, what to write, when to validate, and what mistakes to avoid. Investing in the skill pays back on every agent invocation.

- **Direct file writes are the agent's primary creation mechanism.** When the agent needs to create an issue, it does not call `agent-project issue create`. It reads the schema reference, reads the example file, and uses the `Write` tool to drop a YAML file into `issues/`. The CLI does not stand between the agent and its output.

- **The CLI is minimal: read + validate + atomic operations only.** No `issue create`, `node create`, `session create`, `comment add`. Mutation commands are deferred. The 11 v0 commands are: `init`, `scaffold-for-creation`, `next-key`, `validate`, `status`, `graph`, `refs`, `node check`, `templates`, `enums`, `artifacts`. (See the CLI Commands section.)

- **`agent-project validate` is the gate.** After every batch of agent file writes, the agent runs `validate --strict --format=json`, parses the errors, fixes them, and re-runs until exit code 0. The validator catches ~95% of structural mistakes before they reach a commit. It also rebuilds the graph cache as a side effect, so there is exactly one command and one mental model.

- **Templates ship as readable example files, not as CLI generator inputs.** The PM skill points the agent at `examples/issue-fully-formed.yaml`, `examples/node-endpoint.yaml`, etc. The agent reads them, learns the shape, and produces files that match. There is no `--template default` flag the agent has to remember.

- **`agent-project` is fully standalone first-class.** Useful and polished before anyone touches `agent-containers` or `agent-projects-ui`. The verification target (`project-kb-pivot`) only requires the CLI, the skill, and Claude Code — no orchestration runtime, no UI, no containers. The other layers come later, after v0 ships and the verification passes.

The rest of this document describes the data model, CLI surface, validator, ID system, and skill structure with this primary use case in mind.

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

## ID Allocation — Dual UUID + Sequential Keys

Every entity in the system (Issue, ConceptNode, AgentSession, Comment) carries **two identifiers**: a canonical `uuid` and a human-readable sequential `id`.

### Schema additions

Every entity gains a `uuid` field at the top of its frontmatter:

```yaml
---
uuid: 7c3a4b1d-9f2e-4a8c-b5d6-1e2f3a4b5c6d   # canonical identity, never changes
id: SEI-42                                    # human-readable, may be renamed on collision
...
---
```

The Pydantic models add a `uuid: UUID = Field(default_factory=uuid.uuid4)` field. The default factory means agents can omit the `uuid` field entirely on first write and the model will generate one — but the recommended pattern is for the agent to mint a uuid4 itself when drafting the file, so the value lands in the YAML on the very first save.

### Generation rules

- **UUIDs**: agents generate their own (uuid4) when drafting a file. No CLI call is needed. Two agents picking the same UUID is astronomically unlikely (~2^122 collision space). This avoids any race condition or coordination between concurrent agents.
- **Sequential keys**: agents call `agent-project next-key --type issue` once per new issue (or `--type session`). The CLI takes a file lock on `project.yaml`, reads `next_issue_number`, increments and writes back, releases the lock, and returns the allocated key on stdout. This is atomic across concurrent callers on the same machine.

### Conflict resolution

Key collisions are rare but possible across branches that get merged independently:

1. Branch A creates `issues/SEI-42.yaml` with UUID `aaa-...`
2. Branch B creates `issues/SEI-42.yaml` with UUID `bbb-...`
3. Merge: git reports a conflict on the file
4. Whoever resolves the merge keeps both — but they are now duplicates with conflicting `id`s
5. The validator detects: two files claim `id: SEI-42`, with different UUIDs → error
6. With `--fix`, the validator keeps the file with the most inbound references (or alphabetically-lower UUID as tiebreaker), renames the other to the next free key (e.g. `SEI-50`), and rewrites every `[[SEI-42]]` and `blocked_by: [SEI-42]` reference whose target file has the loser's UUID

The UUID makes the rewrite unambiguous: the validator can identify "every reference to the entity with UUID `bbb-...`" and update those, even though the keys collided. The agent never has to manually resolve key collisions.

### Why dual ID instead of UUID-only

- **Human readability**: `[[user-model]]` and `SEI-42` are the references humans (and agents) actually use in prose, branch names, commit messages, and PR titles. UUIDs are not memorable or pasteable.
- **Backwards compatibility**: existing tooling (Linear-style key references in commit messages, branch names like `claude/SEI-42-auth`) keeps working unchanged.
- **Stable identity across renames**: UUIDs make refactoring safe — splits, merges, key collisions resolve without breaking references, because lookups go through the canonical identity rather than the human label.

### Why not skip `next-key` and let agents read/increment `project.yaml`

- **Race conditions**: two concurrent agents would each read `next_issue_number: 42`, both write `SEI-42`, and produce a collision.
- **Atomicity**: `next-key` is one CLI call, one file lock, one increment, one return. The alternative is three file operations (read, increment, write) the agent has to coordinate.
- **Future-proofing**: centralised allocation makes it easy to extend later for distributed scenarios (e.g. allocating in batches, reserving ranges per agent, or syncing with a remote registry).

The dual model is documented in the PM skill at `references/ID_ALLOCATION.md`, and the anti-patterns doc explicitly forbids hand-writing UUIDs or manually incrementing `project.yaml.next_issue_number`.

---

## The Coherence Problem and the Concept Graph

### Why this matters

The single biggest problem in agent-driven development is **coherence drift**. When an issue says "implement the `/auth/token` endpoint per the API contract," three things can drift independently:

1. The issue description (static once written)
2. The actual code (changes via PRs)
3. The contract document (changes separately)

Nobody notices until an agent picks up a downstream ticket and builds against stale information. This creates cascading failures: wrong API contracts, mismatched schemas, broken integrations — all because the references in tickets are just prose, not live links.

Beyond the integrity problem, drift directly damages agents in two ways:

**Agent confusion**: When the issue, the contract, and the code disagree, the agent has to guess which is authoritative. It often picks wrong, building against stale information. The damage compounds as downstream tickets pick up the wrong version. By the time the contradiction surfaces, it's wedged into multiple PRs.

**Drift fixes burn tokens**: Reconciling drift means finding every location where an old value lives — issues, comments, doc files, code, tests, terraform, schemas — and updating each one. This is exactly the kind of mechanical, repetitive search-and-replace work that LLMs are bad at: they miss instances, they update inconsistently, and they have to re-read enormous amounts of context to find each occurrence. The compute cost is high, the result is imperfect, and the next agent to read the codebase has to deal with whatever stragglers were missed. **Drift is a tax on every future agent invocation.**

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
│       │   ├── validator.py             # The validation gate engine (full check catalogue)
│       │   ├── dependency_graph.py      # Issue dependency graph (from dependency_graph.py)
│       │   ├── concept_graph.py         # Full graph: issues + nodes + edges (unified view)
│       │   ├── status.py                # Status transitions, dashboard aggregation
│       │   ├── id_generator.py          # Sequential <PREFIX>-<N> key generation
│       │   ├── uuid_helpers.py          # NEW: UUID generation + validation helpers (uuid4)
│       │   ├── key_allocator.py         # NEW: atomic next-key allocation under file lock
│       │   ├── enum_loader.py           # Dynamic enum loading from <project>/enums/
│       │   ├── graph_cache.py           # Incremental graph index cache (v2 schema)
│       │   └── pm_review.py             # DEFERRED: PM agent PR review checks (deferred from v0)
│       │   #
│       │   # NOTE: the orchestration RUNTIME lives in the agent-containers package
│       │   # (`agent_containers/core/orchestration.py`), NOT here. The agent-project
│       │   # package owns the data models and CLI for managing patterns; the runtime
│       │   # that reads patterns and dispatches actions ships with agent-containers.
│       │
│       ├── cli/                         # Click CLI — v0 surface only (read + atomic ops)
│       │   ├── __init__.py
│       │   ├── main.py                  # Root group + global options
│       │   ├── init.py                  # `agent-project init` (interactive wizard + flags)
│       │   ├── scaffold.py              # NEW: `agent-project scaffold-for-creation`
│       │   ├── next_key.py              # NEW: `agent-project next-key` (atomic, file-locked)
│       │   ├── validate.py              # `agent-project validate` (the gate; rebuilds cache)
│       │   ├── status.py                # `agent-project status`
│       │   ├── graph.py                 # `agent-project graph` (dependency + concept)
│       │   ├── refs.py                  # `agent-project refs {list,reverse,check}`
│       │   ├── node.py                  # `agent-project node check` (read-only freshness)
│       │   ├── templates.py             # `agent-project templates {list,show}`
│       │   ├── enums.py                 # `agent-project enums {list,show}`
│       │   └── artifacts.py             # `agent-project artifacts {list,show}`
│       │   #
│       │   # DEFERRED (not in v0): cli/issue.py mutation (create/update),
│       │   # cli/session.py mutation (create/update/re-engage), cli/pm.py (review-pr),
│       │   # cli/orchestrate.py (evaluate), cli/comment.py (add). Mutation happens via
│       │   # direct file writes by the agent; the validator catches errors.
│       │
│       ├── templates/                   # Defaults shipped with the package, copied on init
│       │   ├── __init__.py              # Template loader
│       │   ├── project/
│       │   │   ├── project.yaml.j2
│       │   │   ├── CLAUDE.md.j2
│       │   │   └── gitignore.j2
│       │   ├── enums/                   # NEW: customisable enums
│       │   │   ├── issue_status.yaml
│       │   │   ├── priority.yaml
│       │   │   ├── executor.yaml
│       │   │   ├── verifier.yaml
│       │   │   ├── node_type.yaml
│       │   │   ├── node_status.yaml
│       │   │   ├── session_status.yaml
│       │   │   ├── re_engagement_trigger.yaml
│       │   │   ├── message_type.yaml
│       │   │   └── agent_state.yaml
│       │   ├── issue_templates/
│       │   │   ├── default.yaml.j2
│       │   │   ├── bug.yaml.j2
│       │   │   ├── decision.yaml.j2
│       │   │   └── investigation.yaml.j2
│       │   ├── comment_templates/       # NEW: comment scaffolds
│       │   │   ├── status_change.yaml.j2
│       │   │   ├── question.yaml.j2
│       │   │   └── completion.yaml.j2
│       │   ├── artifacts/               # NEW: session output templates
│       │   │   ├── manifest.yaml        # declares the active artifact set
│       │   │   ├── plan.md.j2
│       │   │   ├── task-checklist.md.j2
│       │   │   ├── verification-checklist.md.j2
│       │   │   ├── recommended-testing-plan.md.j2
│       │   │   └── post-completion-comments.md.j2
│       │   ├── agent_templates/         # default agent definitions
│       │   │   ├── backend-coder.yaml
│       │   │   ├── frontend-coder.yaml
│       │   │   ├── verifier.yaml
│       │   │   └── pm.yaml
│       │   ├── session_templates/       # NEW
│       │   │   └── default.yaml.j2
│       │   ├── orchestration/           # NEW: default patterns + hook scaffold
│       │   │   ├── default.yaml
│       │   │   ├── strict.yaml
│       │   │   ├── fast.yaml
│       │   │   └── hooks/
│       │   │       └── __init__.py
│       │   ├── skills/                  # ALL skills, copied into <project>/.claude/skills/
│       │   │   ├── agent-messaging/     # default messaging skill (every agent gets this)
│       │   │   │   ├── SKILL.md
│       │   │   │   └── references/
│       │   │   │       ├── MESSAGE_TYPES.md
│       │   │   │       ├── EXAMPLES.md
│       │   │   │       └── ANTI_PATTERNS.md
│       │   │   ├── project-manager/     # PM agent skill — entry point + references + examples
│       │   │   │   ├── SKILL.md          # ~1 page entry point (terse, scannable)
│       │   │   │   ├── references/       # Loaded on demand (progressive disclosure)
│       │   │   │   │   ├── WORKFLOWS_INITIAL_SCOPING.md
│       │   │   │   │   ├── WORKFLOWS_INCREMENTAL_UPDATE.md
│       │   │   │   │   ├── WORKFLOWS_TRIAGE.md
│       │   │   │   │   ├── WORKFLOWS_REVIEW.md
│       │   │   │   │   ├── SCHEMA_PROJECT.md
│       │   │   │   │   ├── SCHEMA_ISSUES.md
│       │   │   │   │   ├── SCHEMA_NODES.md
│       │   │   │   │   ├── SCHEMA_SESSIONS.md
│       │   │   │   │   ├── SCHEMA_COMMENTS.md
│       │   │   │   │   ├── SCHEMA_ARTIFACTS.md
│       │   │   │   │   ├── CONCEPT_GRAPH.md
│       │   │   │   │   ├── ID_ALLOCATION.md
│       │   │   │   │   ├── VALIDATION.md
│       │   │   │   │   ├── REFERENCES.md
│       │   │   │   │   ├── COMMIT_CONVENTIONS.md
│       │   │   │   │   ├── ANTI_PATTERNS.md
│       │   │   │   │   └── POLICIES.md
│       │   │   │   └── examples/         # Worked examples — canonical truth
│       │   │   │       ├── issue-fully-formed.yaml
│       │   │   │       ├── issue-with-references.yaml
│       │   │   │       ├── node-endpoint.yaml
│       │   │   │       ├── node-model.yaml
│       │   │   │       ├── node-decision.yaml
│       │   │   │       ├── node-config.yaml
│       │   │   │       ├── node-contract.yaml
│       │   │   │       ├── session-single-issue.yaml
│       │   │   │       ├── session-multi-repo.yaml
│       │   │   │       ├── comment-status-change.yaml
│       │   │   │       ├── orchestration-default.yaml
│       │   │   │       └── artifacts/
│       │   │   │           ├── plan.md
│       │   │   │           ├── task-checklist.md
│       │   │   │           └── verification-checklist.md
│       │   │   ├── backend-development/ # default coding agent skill
│       │   │   │   └── SKILL.md
│       │   │   └── verification/        # default verifier skill
│       │   │       └── SKILL.md
│       │   └── standards.md.j2          # NEW: PM review standards (per-project)
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
    │   ├── test_id_generator.py
    │   ├── test_enum_loader.py          # NEW
    │   ├── test_graph_cache.py          # NEW
    │   └── test_pm_review.py            # NEW
    └── integration/
        ├── test_init.py
        ├── test_issue_lifecycle.py
        └── test_node_lifecycle.py
```

---

## Data Model

### Generated Project Directory (output of `agent-project init`)

`agent-project init` copies the entire `templates/` tree from the package into the new project, with template substitution for project name, key prefix, etc. After init, the **project repo is the source of truth** — the `agent-project` package is no longer canonical for these files. The user owns them, edits them freely, and commits them to git.

```
my-project/
├── project.yaml                    # ProjectConfig
├── CLAUDE.md                       # PM agent entry point → skill
├── enums/                          # from templates/enums/  ← all customisable enums
├── issue_templates/                # from templates/issue_templates/
├── comment_templates/              # from templates/comment_templates/
├── templates/
│   └── artifacts/                  # from templates/artifacts/  ← session output templates + manifest
├── agents/                         # from templates/agent_templates/
├── session_templates/              # from templates/session_templates/
├── orchestration/                  # from templates/orchestration/  ← patterns + Python hooks
├── .claude/
│   └── skills/                     # from templates/skills/  ← ALL skills (every agent reads from here)
│       ├── agent-messaging/
│       ├── project-manager/
│       ├── backend-development/
│       └── verification/
├── standards.md                    # from templates/standards.md.j2  ← PM review standards
├── issues/                         # One file per issue
│   └── .gitkeep
├── graph/
│   └── nodes/                      # One file per concept node
│       └── .gitkeep
├── docs/
│   └── issues/                     # Per-issue artifacts (developer.md, verified.md)
│       └── .gitkeep
├── sessions/                       # Agent session directories (see Session Artifacts section)
│   └── .gitkeep
└── .gitignore
```

**Principle: the project repo is the source of truth.** Every Enum, schema, template, skill, orchestration pattern, and rule that ships with `agent-project` is a **default reference** that gets copied into the user's project on `init`. After that, the package is no longer canonical — the project repo is. Two projects can have completely different rules for messaging, completely different artifact sets, completely different orchestration patterns, all fully under their own control and version-controlled.

**`agent-project init --update`** pulls upstream changes from the package's `templates/` into the project selectively, never overwriting user edits without confirmation. This is the upgrade path for projects that want to track new defaults as the package evolves.

`agent-project templates list` and `agent-project templates show <name>` let users explore what ships in the package without leaving the CLI.

### Enums (customisable per project)

Enums are not hardcoded Python `StrEnum` classes. They are YAML files in the project repo at `<project>/enums/<name>.yaml`, copied from packaged defaults at `templates/enums/` on `agent-project init`. After init, the project owns its enums and can add states, rename labels, recolor for the UI, or remove states it doesn't use.

The Pydantic models load enums dynamically at startup via `core/enum_loader.py`, which reads `<project>/enums/*.yaml` if present and falls back to packaged defaults otherwise.

Example enum file:

```yaml
# enums/issue_status.yaml — copied into <project>/enums/issue_status.yaml on init
name: IssueStatus
description: Issue lifecycle states
values:
  - id: backlog
    label: Backlog
    color: gray
  - id: todo
    label: To Do
    color: blue
  - id: in_progress
    label: In Progress
    color: yellow
  - id: verifying
    label: Verifying
    color: orange
  - id: reviewing
    label: Reviewing
    color: purple
  - id: testing
    label: Testing
    color: cyan
  - id: ready
    label: Ready
    color: lime
  - id: updating
    label: Updating
    color: pink
  - id: done
    label: Done
    color: green
  - id: canceled
    label: Canceled
    color: red
```

The complete set of enum files shipped under `templates/enums/`:

| File | Purpose |
|------|---------|
| `issue_status.yaml` | Issue lifecycle states |
| `priority.yaml` | Issue priority (urgent, high, medium, low) |
| `executor.yaml` | Who executes the issue (ai, human, mixed) |
| `verifier.yaml` | Whether verification is required (required, optional, none) |
| `node_type.yaml` | Concept node types (endpoint, model, config, tf_output, contract, decision, requirement, service, schema, custom) |
| `node_status.yaml` | Concept node lifecycle (active, planned, deprecated, stale) |
| `session_status.yaml` | Session lifecycle (planned, active, waiting_for_ci, …, completed, failed) |
| `re_engagement_trigger.yaml` | Why a session was re-engaged (ci_failure, plan_approved, …) |
| `message_type.yaml` | MCP message types — gains a new `status` value (see Section: Status Messages in `agent-containers.md`) |
| `agent_state.yaml` | NEW enum for status messages — see Section: Status Messages in `agent-containers.md` for the full value list (investigating, planning, awaiting_plan_approval, implementing, testing, debugging, refactoring, documenting, self_verifying, blocked, handed_off, done) |

The `AgentState` enum is brand new in this design — it powers the structured `status` message body so the UI can show "what is the agent doing right now" without parsing free-form text. Because it ships as `templates/enums/agent_state.yaml`, projects can extend it with their own states.

### Issue File Format (YAML frontmatter + Markdown body)

```yaml
# issues/PRJ-42.yaml
---
uuid: 7c3a4b1d-9f2e-4a8c-b5d6-1e2f3a4b5c6d
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
docs:
  - docs/auth/jwt-spec.md
  - docs/decisions/DEC-003.md
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

**`Issue.uuid: UUID`** — canonical identity for the issue. Generated by the agent (uuid4) on first write, never changes. The Pydantic model has `uuid: UUID = Field(default_factory=uuid.uuid4)`. The `id` (`PRJ-42`) is the human-readable label and may be renamed during conflict resolution; the `uuid` is the stable handle. See the "ID Allocation — Dual UUID + Sequential Keys" section for the full rationale.

**`Issue.docs: list[str] | None`** — optional doc paths from the project repo, mounted read-only into the container alongside agent-level and session-level docs. The agent definition (`agents/<id>.yaml`) declares its base `context.docs`; the issue can append issue-specific context (e.g. a JWT spec, an ADR); the session can append more on top. All three lists are merged (deduped by path) and mounted at `/workspace/docs/<path>` when the container launches.

### Concept Node File Format

Concept nodes are the core mechanism for coherence. Each node is a named, versioned pointer
to a concrete artifact in the codebase.

```yaml
# graph/nodes/auth-token-endpoint.yaml
---
uuid: 9b5d8e4a-2c1f-4b7e-9d3a-6f8e1c2b4a5d
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

- **`uuid` is the canonical identity.** Generated by the agent (uuid4) on first write, never changes. The Pydantic model has `uuid: UUID = Field(default_factory=uuid.uuid4)`. The `id` slug is the human-readable label and may be renamed during conflict resolution; the `uuid` is the stable handle that all internal lookups go through.
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
uuid: 9b5d8e4a-2c1f-4b7e-9d3a-6f8e1c2b4a5d
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
uuid: 4e7c2a1b-8f5d-49a3-b2c6-3d8e1f9a4b7c
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
uuid: 2a8b3c4d-5e6f-47a1-9b8c-1d2e3f4a5b6c
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
uuid: 6f1e2d3c-4b5a-4e9f-8a7b-6c5d4e3f2a1b
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
uuid: 8c7b6a5d-4e3f-42a1-9c8b-7d6e5f4a3b2c
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
uuid: 3d2c1b4a-5e6f-47b8-9c1d-2e3f4a5b6c7d
id: refresh-endpoint
type: endpoint
name: "POST /auth/refresh"
description: "Token refresh endpoint. Will be implemented in PRJ-48."
status: planned
# No source — code doesn't exist yet
```

**Decision node** — points to a decision record (could be in the project repo itself):
```yaml
uuid: 5b4a3c2d-1e0f-49a8-b7c6-5d4e3f2a1b9c
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

### The graph cache — incrementally maintained lookup index

**Problem**: the implicit edge model means every render needs to recompute by scanning every issue and node file. For projects with hundreds of issues this becomes slow, especially for the UI's graph view which renders constantly. Full rebuilds (`agent-project refs rebuild`) are too expensive to run on every read.

**New approach: incremental cache.** `graph/index.yaml` is committed to git as before, but it is now incrementally updated by the file watcher and CLI commands. Full rebuilds are only needed when the cache is corrupt or missing.

#### Cache schema (v2)

```yaml
# graph/index.yaml
version: 2
last_full_rebuild: "2026-04-07T10:00:00"
last_incremental_update: "2026-04-07T15:33:12"

# Per-file fingerprint — used to detect what's stale on incremental update
files:
  "issues/SEI-42.yaml":
    mtime: 1712512392
    sha: "abc123..."
    references_to: [auth-token-endpoint, user-model, dec-003]
    blocked_by: [SEI-40]
    blocks: []
  "graph/nodes/auth-token-endpoint.yaml":
    mtime: 1712510000
    sha: "def456..."
    related: [user-model]

# Computed lookup tables (the fast read paths)
by_name:
  "POST /auth/token": auth-token-endpoint

by_type:
  endpoint: [auth-token-endpoint, refresh-endpoint]
  model: [user-model]

referenced_by:
  auth-token-endpoint: [SEI-42, SEI-45]
  user-model: [SEI-40, SEI-42]

# Edges (computed once, served fast)
edges:
  - from: SEI-42
    to: auth-token-endpoint
    type: references
  - from: SEI-42
    to: SEI-40
    type: blocked_by
  - from: auth-token-endpoint
    to: user-model
    type: related

stale_nodes: []
last_freshness_check: "2026-04-07T15:00:00"
```

#### Incremental update algorithm

`agent_project/core/graph_cache.py`:

```python
def update_cache_for_file(dir, rel_path):
    """Called by file watcher on file change."""
    cache = load_index(dir)

    # Remove old edges from this file
    cache.edges = [e for e in cache.edges if e.source_file != rel_path]
    cache.files.pop(rel_path, None)

    # If file still exists, parse and re-add
    full_path = dir / rel_path
    if full_path.exists():
        if rel_path.startswith("issues/"):
            issue = load_issue(dir, key_from_path(rel_path))
            cache.files[rel_path] = fingerprint(full_path, issue)
            cache.edges.extend(issue_edges(issue))
        elif rel_path.startswith("graph/nodes/"):
            node = load_node(dir, id_from_path(rel_path))
            cache.files[rel_path] = fingerprint(full_path, node)
            cache.edges.extend(node_edges(node))

    # Rebuild lookup tables (cheap — they're derived from files dict + edges)
    cache.by_name = build_by_name(cache.files)
    cache.by_type = build_by_type(cache.files)
    cache.referenced_by = build_referenced_by(cache.edges)

    cache.last_incremental_update = now()
    save_index(dir, cache)
```

#### Who triggers updates

1. **`agent-project validate`** — the primary trigger. Since validate is the gate the agent runs after every batch of writes, the cache is rebuilt as a side effect on every validation pass. In v0 this is the only path the agent needs to know about.
2. **File watcher (UI backend, future)** — `watchdog` will trigger incremental rebuilds for any file changed in `issues/`, `graph/nodes/`, `sessions/`. Relevant once the UI exists.
3. **Future CLI mutation commands** — when deferred commands like `issue create` are added, they will call `update_cache_for_file()` after saving the file. Not relevant in v0.

#### Reads are now O(1)

`agent-project graph`, the UI's `/api/projects/:id/graph` endpoint, and all `refs *` commands read directly from `graph/index.yaml` without rescanning the project. The result: O(1) graph reads instead of O(N) for N issues + nodes.

#### Concurrency

A single SQLite write-ahead lock file (`graph/.index.lock`) prevents concurrent writes from corrupting the cache. Reads are unaffected (cache is just YAML).

#### Edge model unchanged

The implicit edge philosophy stays — edges are still derived from `[[references]]` in bodies and `blocked_by`/`related` in frontmatter. The cache is purely a performance layer; deleting it always rebuilds correctly. The cache is never the source of truth — it's a derived view of the underlying files.

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
uuid: 1a2b3c4d-5e6f-47a8-9b0c-1d2e3f4a5b6c
issue_key: PRJ-42
author: claude
type: status_change
created_at: "2026-03-26T15:30:22"
---
Starting work on PRJ-42. Created branch `claude/PRJ-42-auth-endpoint`.

No blockers. PRJ-40 merged yesterday. [[user-model]] is available in test branch.
```

**`Comment.uuid: UUID`** — canonical identity for the comment. Generated by the agent (uuid4) on first write, never changes. The Pydantic model has `uuid: UUID = Field(default_factory=uuid.uuid4)`. See the "ID Allocation — Dual UUID + Sequential Keys" section.

Comments can also contain `[[references]]` — this is how agents document which concepts
they're working with, and it feeds the reference index.

### AgentSession Model

Sessions carry runtime state across container re-engagements. The session YAML is the
persistence anchor — it tracks what the agent has done and why it was re-engaged.

```yaml
# sessions/wave1-agent-a.yaml
---
uuid: 7e6d5c4b-3a2f-41e8-9d7c-6b5a4f3e2d1c
id: wave1-agent-a
name: "Agent A: Auth + User Model"
agent: backend-coder                  # references agents/backend-coder.yaml
issues: [PRJ-40, PRJ-42]
wave: 1

# Multi-repo: every repo the session can branch and PR in. All equal, all writable.
repos:
  - repo: SeidoAI/web-app-backend
    base_branch: test
    branch: claude/SEI-40-auth          # set after first push
    pr_number: 42                       # set after PR opened
  - repo: SeidoAI/web-app-infrastructure
    base_branch: test
    branch: claude/SEI-40-tf-secrets
    pr_number: 18

# Optional session-level extra docs, merged with agent + issue docs
docs:
  - docs/integration/cross-service-flow.md

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

# Latest agent state from the most recent `status` message (see Section: Status messages).
# Updated by the orchestration runtime each time a status message arrives.
current_state: implementing

# Orchestration override — pick a different pattern, or override individual fields.
# Project default lives in project.yaml; session can override either way.
orchestration:
  pattern: default                    # references orchestration/default.yaml in project repo
  overrides:
    plan_approval_required: true
    auto_merge_on_pass: false

# Artifact overrides for this session — add or remove artifacts beyond the project default
# manifest at templates/artifacts/manifest.yaml.
artifact_overrides:
  - name: architecture-diff
    file: architecture-diff.md
    template: architecture-diff.md.j2
    produced_at: completion
    required: true

# Runtime state — persisted across container restarts. Multi-repo: branch + PR live in
# the per-repo RepoBinding above; the runtime_state holds session-wide handles.
runtime_state:
  claude_session_id: "sess_abc123"    # for claude --resume
  langgraph_thread_id: null           # for langgraph checkpoint resume
  workspace_volume: "vol-wave1-a"     # Docker volume name

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

**Schema notes:**

- **`uuid: UUID`** — canonical identity for the session. Generated by the agent (uuid4) on first write, never changes. The Pydantic model has `uuid: UUID = Field(default_factory=uuid.uuid4)`. The `id` (slug, e.g. `wave1-agent-a`) is the human-readable label. See the "ID Allocation — Dual UUID + Sequential Keys" section.

- **`repos: list[RepoBinding]`** replaces the old single `repo: str`. All repos are equal — there is no primary. The agent treats them symmetrically, can branch in any, and opens PRs against any. The session tracks one PR per repo. The `RepoBinding` model lives in `models/session.py`:

  ```python
  class RepoBinding(BaseModel):
      repo: str                            # GitHub slug
      base_branch: str
      branch: str | None = None
      pr_number: int | None = None
  ```

- **`docs: list[str] | None`** — session-level extra docs. Merged with the agent definition's `context.docs` and every issue's `docs` field, deduped by path, and mounted read-only at `/workspace/docs/<path>` in the container.

- **`current_state: str | None`** — the latest agent state from a `status` message (see the Status Messages section in `agent-containers.md`). The orchestration runtime writes this back to the session YAML each time a new status message arrives so the UI can render it without subscribing to the live stream.

- **`orchestration: { pattern: str, overrides: dict }`** — overrides for the project's default orchestration pattern. The hierarchy is **Project → Session** (just two tiers). `project.yaml` declares `orchestration.default_pattern` plus global flags; the session can either pick a different named pattern (`pattern: strict`) or override individual fields (`overrides: {plan_approval_required: true}`). Session-level fields win — straight field-level override, no deeper merging.

- **`artifact_overrides: list[ArtifactSpec]`** — per-session artifact overrides on top of the project's `templates/artifacts/manifest.yaml`. Use this to add session-specific artifacts (e.g. `architecture-diff.md`) or to mark something not required for one session.

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
    ├── messages.yaml                 # message log (committed on session complete)
    └── artifacts/                    # the agent's structured outputs (see Session Artifacts)
        ├── plan.md
        ├── task-checklist.md
        ├── verification-checklist.md
        ├── recommended-testing-plan.md
        └── post-completion-comments.md
```

New CLI command:
```
agent-project session finalize <session-id>
  --messages-file TEXT   Path to messages JSON (from UI backend SQLite export)
  # Writes messages.yaml to session directory and commits to project repo.
  # Called by UI backend when session completes.
```

---

## Session Artifacts

Sessions produce structured Markdown outputs in addition to their message log. Five artifacts ship as defaults; **the set is customisable per project** via `templates/artifacts/manifest.yaml`. Projects can add, remove, or reshape artifacts. All artifacts are written by the agent to `sessions/<id>/artifacts/` in the project repo and committed via the agent's PR.

### The five default artifacts

**1. `plan.md`** — equivalent of Claude Code's plan output. Free-form Markdown produced by the agent during its planning phase. May reference `[[concept-nodes]]`. This is the candidate for plan approval gating.

**2. `task-checklist.md`** — explicit Markdown table the agent maintains as it works:

```markdown
# Task Checklist — wave1-agent-a

| # | Task | Status | Comments |
|---|------|--------|----------|
| 1 | Add JWT validation middleware | done | Used `python-jose`. See [[auth-token-endpoint]]. |
| 2 | Wire middleware into auth router | done | — |
| 3 | Add unit tests for valid/invalid/expired tokens | in_progress | Discovered an existing test fixture I can reuse. |
| 4 | Update OpenAPI contract | blocked | Waiting for contract decision from human (msg #003). |
| 5 | Add migration for `last_login` field | done | Outside scope but trivial; flagged in comment. |
```

Status values: `pending | in_progress | done | blocked | skipped`. Comments capture decisions, deviations, problems, external dependencies (in or out), or anything noteworthy.

**3. `verification-checklist.md`** — Markdown checklist the agent generates during planning and ticks off at the end:

```markdown
# Verification Checklist — wave1-agent-a

- [x] All acceptance criteria from SEI-40 met
- [x] All acceptance criteria from SEI-42 met
- [x] Unit tests pass locally (`uv run pytest`)
- [x] Lint passes (`make lint`)
- [x] No hardcoded secrets
- [x] Concept nodes created/updated for new artifacts
- [x] developer.md and verified.md drafts written
```

**4. `recommended-testing-plan.md`** — written near the end. Tells the human reviewer (and any downstream verifier agent) what should be tested manually or in higher environments, beyond what CI covers. Includes scenarios, edge cases, environment requirements, suggested commands.

```markdown
# Recommended Testing Plan — wave1-agent-a

## Manual / exploratory checks
1. Log in with a valid Firebase account; confirm JWT issued and 1-hour expiry
2. Replay an expired JWT; confirm 403 with the standard error envelope
3. Hit `/auth/token` from the frontend SPA on test env (not just curl)

## Environment-specific
- Verify `JWT_SECRET` is set in test env via `gcloud secrets versions list`
- Confirm rate limiting kicks in after 5 attempts/minute (manual)

## Regression watchlist
- Existing `/auth/refresh` should still work — not touched in this PR but shares middleware
```

**5. `post-completion-comments.md`** — written at the very end. The agent's reflective notes: decisions made, things deferred, surprises encountered, follow-ups for later. Used by the PM agent when triaging follow-up issues, and by humans during review.

```markdown
# Post-Completion Comments — wave1-agent-a

## Decisions
- Chose `python-jose` over `pyjwt` because it has built-in JWE support that we'll need for SEI-58.
- Used a constant-time comparison helper from `secrets` module instead of `==`.

## Deferred
- Did not implement `/auth/refresh` — that's SEI-48 and out of scope here.
- Did not migrate the `last_login` field on existing users; needs a one-off backfill script (suggest opening a follow-up issue).

## Surprises
- The existing `auth_middleware.py` had a stale comment claiming JWTs were stored in localStorage. They are not. Updated the comment.

## Follow-ups (suggested for PM)
- Open issue: backfill `last_login` for existing users
- Open issue: deprecate the unused `legacy_auth.py` module
```

### The artifact manifest

`templates/artifacts/manifest.yaml` declares the active artifact set and when each is produced:

```yaml
# templates/artifacts/manifest.yaml
artifacts:
  - name: plan
    file: plan.md
    template: plan.md.j2
    produced_at: planning           # planning | implementing | completion
    required: true
    approval_gate: false            # set true to enable plan approval

  - name: task-checklist
    file: task-checklist.md
    template: task-checklist.md.j2
    produced_at: planning           # initial table created at planning, updated through implementing
    required: true

  - name: verification-checklist
    file: verification-checklist.md
    template: verification-checklist.md.j2
    produced_at: planning           # generated then confirmed at completion
    required: true

  - name: recommended-testing-plan
    file: recommended-testing-plan.md
    template: recommended-testing-plan.md.j2
    produced_at: completion
    required: true

  - name: post-completion-comments
    file: post-completion-comments.md
    template: post-completion-comments.md.j2
    produced_at: completion
    required: true
```

Schema fields per artifact entry: `name`, `file`, `template`, `produced_at`, `required`, `approval_gate`.

Projects can:
- Add new artifacts (e.g. `architecture-diff.md`, `performance-notes.md`)
- Remove ones they don't need (set `required: false` or delete the entry)
- Reshape templates entirely
- Add their own `produced_at` phases if their workflow has more stages

Sessions can override via the `artifact_overrides` field on the session YAML — adding extra artifacts or marking some as not required for that specific session.

### Plan approval gate

Set `approval_gate: true` on the `plan` artifact (or any artifact) to make the agent stop after producing it and send a `plan_approval` message. The orchestrator only re-engages once approval is received. This is the mechanism by which a project (or single session) opts into human-in-the-loop plan review.

### PM agent enforcement

The PM agent's PR review (see "PM PR Review" section below) checks that all artifacts marked `required: true` in `templates/artifacts/manifest.yaml` are present before approving a session-completion PR. The skill instructions for coding agents tell them to read `templates/artifacts/manifest.yaml` to know what they must produce.

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

### `core/validator.py` — The Validation Gate (engine)
- Implements the full check catalogue used by `agent-project validate`
- Returns a structured `ValidationResult` (errors, warnings, fixed entries) suitable for both human-readable and JSON output
- Always rebuilds `graph/index.yaml` as a side effect (delegates to `core/graph_cache.py`)
- Implements the `--fix` auto-fix subset
- See **"The Validation Gate"** section below for the full spec, check catalogue, JSON output schema, auto-fix scope, and rationale

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

### `core/enum_loader.py` — Dynamic Enum Loading
- `load_enums(project_dir) -> dict[str, Enum]` — read every YAML file under `<project>/enums/`, build a `StrEnum` for each, fall back to packaged defaults from `templates/enums/` for any enum not present in the project
- Pydantic models import their enums via this loader at module init time so projects can extend `IssueStatus`, `AgentState`, `MessageType`, etc., without forking the package

### `core/graph_cache.py` — Incremental Graph Index
- See the "Graph cache" section below for the v2 schema and the `update_cache_for_file` algorithm
- `load_index(dir) -> GraphIndex`, `save_index(dir, cache)`, `update_cache_for_file(dir, rel_path)`, `full_rebuild(dir)`
- Uses a SQLite write-ahead lock file (`graph/.index.lock`) to keep concurrent writes from corrupting the cache

### `core/pm_review.py` — PM Agent PR Review Checks
- See the "PM PR Review" section below for the full check list
- Each check is a function returning `CheckResult(name, passed, details, fix_hint)`
- Run by `agent-project pm review-pr <pr-number>` against the diff of a project-repo PR

---

## The Validation Gate

`agent-project validate` is the single most important command in the system. It is the gate the agent runs after every batch of file writes, and the loop converges only when validate exits clean. Investing in validate quality is the highest-leverage thing in the whole library.

### Behaviour

```
agent-project validate [--strict] [--format=text|json] [--fix]
```

- Walks the entire project repo
- Loads `project.yaml`, all `enums/*.yaml`, all `issues/*.yaml`, all `graph/nodes/*.yaml`, all `sessions/*.yaml`, `templates/artifacts/manifest.yaml`, and all `orchestration/*.yaml`
- Runs every check in the check catalogue (below)
- **Always rebuilds `graph/index.yaml` as a side effect** (incremental if possible, full rebuild if needed)
- Exits `0` if clean, `1` if only warnings, `2` if any errors
- `--strict` treats warnings as errors (the agent's normal mode)
- `--fix` auto-fixes a defined subset of issues (see "Auto-fix scope" below)

### Check catalogue

**Schema checks** (one error per violation):
- Every `.yaml` file in `issues/` parses as YAML and matches the `Issue` Pydantic model
- Same for `graph/nodes/`, `sessions/`, comments, artifacts metadata
- `project.yaml` matches the `ProjectConfig` model
- Every entity has a `uuid` field with a valid UUID4
- Every `issue.id` matches the `<PREFIX>-<N>` pattern from `project.yaml.key_prefix`
- Every required frontmatter field is present
- Every enum-typed field has a value present in the active enum (loaded from `enums/`)

**Reference integrity**:
- Every `[[node-id]]` in any markdown body resolves to a node file
- Every `blocked_by: [...]` entry references an existing issue
- Every `parent: X` references an existing issue
- Every `related: [...]` on a node references an existing node
- Every `repo: X` in an issue or session references a repo declared in `project.yaml.repos`
- Every `agent: X` in a session references an agent definition in `agents/`

**Bi-directional consistency**:
- For every `node A.related: [B]`, `node B.related` must also contain `A`. Auto-fixable with `--fix`.
- For every `issue A.blocked_by: [B]`, the index correctly computes `B.blocks: [A]` (validator updates the cache; no error unless mismatch is found in the stored cache).

**Issue body structure**:
- Required Markdown headings present: `Context`, `Implements`, `Repo scope`, `Requirements`, `Execution constraints`, `Acceptance criteria`, `Test plan`, `Dependencies`, `Definition of Done`
- Acceptance criteria has at least one checkbox item
- "Stop and ask" guidance present somewhere in body
- Warns if the issue contains zero `[[references]]` (potential coherence gap — issues should reference concept nodes)

**Status transition validity**:
- Every issue's `status` is reachable from `backlog` via the transitions in `project.yaml.status_transitions`
- Every session's `status` is in the active session-status enum

**Concept node freshness**:
- For every `active` node with a `source`, fetch current content (local clone or GitHub API), hash, compare
- Mismatch → warning (or error with `--strict`)
- Missing source file → error

**Artifact presence**:
- For every session in `completed` status, every artifact marked `required: true` in `templates/artifacts/manifest.yaml` exists in `sessions/<id>/artifacts/`

**ID collision detection** (the UUID dual-ID system):
- Two files claim the same `id` but have different `uuid` → error, with both file paths reported
- Auto-fixable with `--fix`: rename one to the next free key, rewrite all references via UUID lookup

**Sequence drift**:
- `project.yaml.next_issue_number` is at least `max(existing issue keys) + 1`
- Auto-fixable with `--fix`

**Timestamps**:
- `created_at` and `updated_at` parseable as ISO datetime
- Auto-fixable with `--fix` (fill missing `updated_at` with file mtime)

**Comment provenance**:
- Every comment has `author`, `type`, `created_at`
- `type` is in the active comment-type enum

**Project standards**:
- Read `<project>/standards.md` if present and apply project-defined rules (initial v0: just check the file exists if referenced)

### JSON output schema

```json
{
  "version": 1,
  "exit_code": 2,
  "summary": {
    "errors": 3,
    "warnings": 1,
    "fixed": 2,
    "cache_rebuilt": true,
    "duration_ms": 123
  },
  "errors": [
    {
      "code": "ref/dangling",
      "severity": "error",
      "file": "issues/SEI-42.yaml",
      "line": 18,
      "field": "body",
      "message": "Reference [[user-modle]] does not resolve to any node",
      "fix_hint": "Did you mean [[user-model]]? Or create a node 'user-modle' in graph/nodes/."
    }
  ],
  "warnings": [],
  "fixed": [
    {
      "code": "timestamp/missing",
      "file": "issues/SEI-43.yaml",
      "field": "updated_at",
      "before": null,
      "after": "2026-04-07T16:00:00"
    }
  ]
}
```

The fixed JSON schema lets the agent parse errors, locate the file/field, and apply fixes without re-reading the human-readable output.

### Auto-fix scope

`--fix` handles:
- Missing `created_at` / `updated_at` → fill from file mtime
- Drifted `next_issue_number` → bump to `max(existing keys) + 1`
- Missing `uuid` → generate uuid4 and add
- Bi-directional `related` mismatch on nodes → add the missing side
- Sorted-list normalisation (labels, related)
- ID collisions → rename one (fewest references wins) and rewrite refs
- Stale graph cache → rebuild

`--fix` does NOT touch:
- Issue body content (no field invention)
- Reference targets (the agent decides what to reference)
- Anything that affects semantic intent

### Cache rebuild logic

- If `graph/index.yaml` is missing or version-mismatched → full rebuild
- If `last_incremental_update` is older than the most recent file mtime in `issues/` or `graph/nodes/` → incremental rebuild for the changed files
- Otherwise → no rebuild needed
- Either way, `validate` reports `cache_rebuilt: true|false` in the JSON output

### Why the gate matters

The agent's loop is:

```
read context
draft files
write files
validate
fix errors
validate
fix errors
validate (clean)
commit
```

If `validate` is rigorous, the loop converges quickly and produces clean output. If `validate` is sloppy, errors leak into commits and surface much later (PR review time, agent-containers launch time, CI failure). Every check in the catalogue is something the validator catches that would otherwise be the agent's problem to remember and the human's problem to clean up.

---

## Orchestration Patterns

Orchestration patterns codify *who acts when*: PM auto-launches vs human approves, plan gate enabled or not, verifier required or skipped, auto-merge on green, etc. Different projects and sessions need different patterns. The patterns themselves are project-owned YAML (with optional Python hook scripts as an escape hatch), version-controlled in the project repo.

**Important: the orchestration runtime lives in `agent-containers`, not `agent-project`.** The runtime is the engine that reads patterns and dispatches actions on every event. The `agent-project` package owns the data models, the templates that ship as defaults, and the CLI for managing patterns. This matches the broader principle: the project repo is the configuration; `agent-containers` is the engine that executes that configuration. The runtime reads from the project repo on every event.

### File layout

```
my-project/
├── orchestration/
│   ├── default.yaml          # project default pattern (used unless overridden)
│   ├── strict.yaml           # named alternative (max human gates)
│   ├── fast.yaml             # named alternative (auto-everything)
│   └── hooks/                # Python hook scripts (optional escape hatch)
│       ├── __init__.py
│       └── custom_verifier.py
```

These are copied from `templates/orchestration/` on `agent-project init`. After init the project owns them — edit, add, remove freely.

### YAML rule format

```yaml
# orchestration/default.yaml
name: default
description: Standard project default — PM auto-orchestrates with human gates only on plan approval

events:
  session_started:
    actions:
      - require_artifact: plan.md
      - if: project.plan_approval_required
        then:
          - send_message: { type: plan_approval, priority: blocking }
          - wait_for: human_response
        else:
          - continue

  plan_approved:
    actions:
      - re_engage: { trigger: plan_approved }

  ci_failure:
    actions:
      - re_engage: { trigger: ci_failure, context_from: ci_logs }

  pr_opened:
    actions:
      - launch_agent: verifier
      - on_verifier_pass:
          - if: project.auto_merge_on_pass
            then: [ merge_pr ]
            else: [ notify_human ]
      - on_verifier_fail:
          - re_engage: { trigger: verifier_rejection, context_from: verifier_review }

  human_review_changes:
    actions:
      - re_engage: { trigger: human_review_changes, context_from: pr_comments }

  status_message_received:
    actions:
      - update_session_status_summary: { from: message }

  artifact_updated:
    when: artifact == "task-checklist.md"
    actions:
      - publish_to_ui

# Optional: call out to a Python hook for complex logic
hooks:
  pre_re_engage: hooks.custom_verifier.maybe_skip_verifier
```

### Built-in actions (the action vocabulary)

| Action | Effect |
|--------|--------|
| `re_engage` | Calls `agent-project session re-engage` + `agent-containers launch` |
| `launch_agent` | Spawns a new container for a named agent (e.g. verifier) |
| `send_message` | Posts to UI message inbox |
| `wait_for` | Pauses the orchestrator until an event happens |
| `merge_pr` | `gh pr merge` |
| `notify_human` | UI desktop notification |
| `require_artifact` | Asserts the agent has produced a named artifact |
| `update_session_status_summary` | Writes status state + summary back to session.yaml |
| `publish_to_ui` | Broadcasts an event over WebSocket |
| `if/then/else` | Conditional branch on `project.<field>` or `session.<field>` |

### Hook scripts (Python escape hatch)

Hooks live in `<project>/orchestration/hooks/*.py` and are invoked by name from the YAML. Signature:

```python
# orchestration/hooks/custom_verifier.py
from agent_project.orchestration import Event, Context

def maybe_skip_verifier(event: Event, ctx: Context) -> dict:
    """Skip verifier for trivial PRs (e.g. only docs changed)."""
    if all(f.endswith('.md') for f in ctx.pr_files):
        return {"skip": True}
    return {"skip": False}
```

The hook receives the event and a context object (session, PR, message, etc.) and returns a dict the orchestrator merges into its decision state.

### Hierarchy: Project → Session

Just two tiers — no agent-tier or issue-tier overrides. This keeps the mental model simple: there is a project default, and any session may override it.

Project default (in `project.yaml`):

```yaml
# project.yaml
orchestration:
  default_pattern: default       # references orchestration/default.yaml
  plan_approval_required: false  # global default
  auto_merge_on_pass: false      # global default
```

Session override: a session can pick a different pattern OR override individual fields.

```yaml
# sessions/wave1-agent-a.yaml
orchestration:
  pattern: strict                # use orchestration/strict.yaml instead
  # OR override individual fields:
  overrides:
    plan_approval_required: true
    auto_merge_on_pass: false
```

Session-level fields *win* over project-level fields. No deeper merging — straight field-level override.

### Example session that overrides

```yaml
# sessions/critical-prod-fix.yaml — wants extra gates
orchestration:
  pattern: default
  overrides:
    plan_approval_required: true     # require human approval before code
    auto_merge_on_pass: false        # no auto-merge even if CI green
```

### Where the orchestration runtime runs

The runtime module (`agent_containers/core/orchestration.py`) reacts to events from:
- File watcher on the project repo (issue/session/artifact changes)
- WebSocket messages (agent status updates from running containers)
- GitHub webhook polling (CI status, PR reviews)
- MCP messages from agents (plan ready, status updates, blocking questions)

It exposes:
- `load_pattern(project_dir, name)` — reads `<project>/orchestration/<name>.yaml`
- `merge_overrides(pattern, session)` — applies session-level overrides on top of project default
- `evaluate_event(pattern, event, ctx)` — looks up matching event in the YAML, evaluates conditions, returns action list
- `run_action(action, ctx)` — executes a built-in action (re_engage, launch_agent, etc.)
- `call_hook(hook_name, event, ctx)` — invokes a Python hook from `<project>/orchestration/hooks/`

The PM agent is a Claude-driven container that can also call into the orchestrator (via the agent-project CLI or directly) for higher-level reasoning. The deterministic orchestrator handles the simple event → action flows; the PM agent handles judgement-heavy decisions (plan review, scope changes, conflict resolution).

`agent-project orchestrate evaluate <event-file>` lets users dry-run an event against the project's patterns from the command line — useful for debugging.

---

## PM PR Review

Coding agents push PRs to *target repos* (web-app-backend, etc.) AND PRs to the *project repo* (containing updates to issues, sessions, nodes, comments, artifacts). The PM agent's job is to review the project-repo PRs.

### What the PM agent checks

When a coding agent opens a PR to the project repo, the PM agent runs the following checks via `core/pm_review.py`. Each check is a function returning `CheckResult(name, passed, details, fix_hint)`.

1. **Schema validation** — every changed YAML file passes pydantic validation (using the project's loaded enums)
2. **Reference integrity** — all `[[node-id]]` references in changed files resolve to existing nodes
3. **Status transition validity** — issue/session status transitions match `project.yaml` rules
4. **Required-fields check** — issues have all required frontmatter (executor, verifier, repo, etc.)
5. **Markdown structure** — issue bodies have all required sections (Context, Acceptance criteria, etc.)
6. **Concept node freshness** — newly added/edited nodes have valid `source` (file exists, hash computed)
7. **Artifact presence** — sessions in `completed` state have all artifacts marked `required: true` in `templates/artifacts/manifest.yaml` (default set: `plan.md`, `task-checklist.md`, `verification-checklist.md`, `recommended-testing-plan.md`, `post-completion-comments.md`)
8. **No orphan additions** — new nodes are referenced by at least one issue or marked `planned`
9. **Comment provenance** — new comments have valid author + type
10. **Project standards** — rules in `<project>/standards.md` (free-form Markdown rules — generated from `templates/standards.md.j2` on init)

The artifact-presence check (#7) reads `templates/artifacts/manifest.yaml` from the project repo, so it automatically respects per-project customisation: if a project removed `recommended-testing-plan.md` from its manifest, the PM does not require it.

If all pass: PM posts an approval review on the PR. If `auto_merge_on_pass` is enabled in orchestration, the PM merges.

If any fail: PM posts a `request_changes` review with specific feedback per check, and the orchestrator re-engages the coding agent with the failing checks as context.

### CLI

```
agent-project pm review-pr <pr-number>
  --repo TEXT          Project repo (GitHub slug) [required]
  --format TEXT        rich/json [default: rich]
  # Runs all 10 checks against the diff. Prints results. Returns nonzero on failures.
  # The PM agent (containerised or not) calls this.
```

---

## CLI Commands

This is the complete v0 CLI surface: **11 commands, all read-only or atomic-operation**. There are no mutation commands like `issue create`, `node create`, or `session create`. Those are deferred to a later release. Agents create entities by writing files directly with the `Write` tool, then run `validate` to confirm correctness.

### `agent-project init`

Interactive wizard by default; takes flags for scripted use.

```
agent-project init
  --name TEXT             Project name (prompts if not provided)
  --key-prefix TEXT       Issue key prefix, e.g. SEI, PKB (prompts if not provided)
  --base-branch TEXT      Default base branch (prompts; defaults to test)
  --repos TEXT            Comma-separated GitHub slugs (prompts; blank to skip)
  --no-git                Skip git init
  --non-interactive       Fail instead of prompting if any required arg is missing
```

The wizard creates the full project scaffold: `project.yaml`, `CLAUDE.md`, `enums/`, `issue_templates/`, `comment_templates/`, `templates/artifacts/`, `agents/`, `orchestration/`, `.claude/skills/` (PM, agent-messaging, backend-development, verification), `standards.md`, and the empty top-level directories (`issues/`, `graph/nodes/`, `sessions/`, `docs/`).

### `agent-project scaffold-for-creation`

Front-loads the agent's context in a single tool call. The PM skill instructs agents to run this before doing anything else.

```
agent-project scaffold-for-creation
  --format TEXT           text/json [default: text]
```

Prints (in one message) the project info, next available IDs, active enums, active artifact manifest, active orchestration pattern, template paths, skill example paths, the validation gate command, and the ID allocation rules. See the "scaffold-for-creation" section below for the full output format.

### `agent-project next-key`

Atomic sequential key allocation under a file lock.

```
agent-project next-key
  --type TEXT             issue/session [default: issue]
  --count INT             How many to allocate at once [default: 1]
```

Atomically increments `project.yaml.next_issue_number` (or session counter) under a file lock. Returns the allocated key(s) on stdout, one per line. The agent calls this once per entity it intends to create.

### `agent-project validate`

The gate. Run after every batch of writes.

```
agent-project validate
  --strict                Treat warnings as errors
  --format TEXT           text/json [default: text]
  --fix                   Auto-fix trivial issues (timestamps, sequence drift, sorted lists, etc.)
```

**Always rebuilds `graph/index.yaml` as a side effect** (incrementally if possible, full rebuild if needed). Exit codes: `0` = clean, `1` = warnings only, `2` = errors. JSON output schema: `{ errors: [...], warnings: [...], fixed: [...], cache_rebuilt: bool, summary: {...} }`. See "The Validation Gate" section for the full check catalogue and JSON schema.

### `agent-project status`

Read-only dashboard.

```
agent-project status
  --format TEXT           rich/json [default: rich]
```

Shows counts by status / executor / priority, blocked issues, stale references, critical path summary, recent activity (from git log).

### `agent-project graph`

Read-only graph rendering. Reads from `graph/index.yaml` (rebuilt by `validate`).

```
agent-project graph
  --type TEXT             deps/concept [default: deps]
  --format TEXT           mermaid/dot/json [default: mermaid]
  --output TEXT           Output file path (default: stdout)
  --status-filter TEXT    Only include issues with these statuses
```

### `agent-project refs list / reverse / check`

Read-only reference inspection.

```
agent-project refs list <issue-key>
  # Show all [[references]] in this issue with freshness status.

agent-project refs reverse <node-id>
  # Show all issues/nodes that reference this node.

agent-project refs check
  # Full scan: report stale references, orphan nodes, dangling refs.
  --format TEXT           table/json [default: table]
```

### `agent-project node check`

Read-only freshness check. Fetches current content (local clone or GitHub API), hashes, compares to stored `content_hash`.

```
agent-project node check [node-id]
  # If node-id omitted, checks all active nodes with sources.
  --format TEXT           table/json [default: table]
```

This is read-only — there is no `--update` flag in v0. Stale nodes are reported; the agent decides whether to edit the node file (using the `Write`/`Edit` tools) and re-run `validate`.

### `agent-project templates list / show`

Read-only exploration of the templates that ship in this project.

```
agent-project templates list
agent-project templates show <name>
```

### `agent-project enums list / show`

Read-only exploration of the active enums (loaded from `<project>/enums/` if present, else from packaged defaults).

```
agent-project enums list
agent-project enums show <name>
```

### `agent-project artifacts list / show`

Read-only inspection of session artifacts.

```
agent-project artifacts list <session-id>
agent-project artifacts show <session-id> <artifact-name>
```

### What's NOT in v0

The following commands are intentionally absent from v0 and listed in the "Deferred features" section: `issue {create,update}`, `node {create,update}`, `session {create,update,re-engage}`, `comment add`, `pm review-pr`, `orchestrate evaluate`, `migrate`, `init --update`, `--watch` mode, `node import-from-code`. Mutation happens via direct file writes; the validator catches errors.

---

## scaffold-for-creation

`agent-project scaffold-for-creation` is the single command an agent runs FIRST when starting a session against a project. It loads all the static context the agent needs into one tool-call result, so the agent doesn't have to re-read 15 files individually.

### Purpose

Front-load the agent's context. One CLI call returns: project config summary, next available IDs, the active enums and their values, the active artifact manifest, the active orchestration pattern, paths to all templates, paths to skill examples, the validation gate command, and the ID allocation rules. The PM skill instructs the agent to run this command first, read the output, and only then begin reading planning docs and drafting files.

### Output (text format, default)

```
PROJECT: project-kb-pivot (PKB)
Description: Pivot from monolithic KB to graph-based knowledge base
Base branch: main
Repos:
  - SeidoAI/web-app-backend          (local: ~/Code/seido/web-app)
  - SeidoAI/web-app-frontend         (local: ~/Code/seido/web-app)
  - SeidoAI/web-app-infrastructure   (local: ~/Code/seido/web-app)

NEXT IDS:
  next issue key: PKB-1
  next session key: (slug-based, no sequence)
  next node id: (slug-based, no sequence)

ACTIVE ENUMS (from enums/):
  issue_status: backlog, todo, in_progress, verifying, reviewing, testing, ready, updating, done, canceled
  priority: urgent, high, medium, low
  executor: ai, human, mixed
  verifier: required, optional, none
  node_type: endpoint, model, config, tf_output, contract, decision, requirement, service, schema, custom
  node_status: active, planned, deprecated, stale
  session_status: planned, active, waiting_for_ci, waiting_for_review, waiting_for_deploy, re_engaged, completed, failed
  message_type: question, plan_approval, progress, stuck, escalation, handover, fyi, status
  agent_state: investigating, planning, awaiting_plan_approval, implementing, testing, debugging, refactoring, documenting, self_verifying, blocked, handed_off, done

ACTIVE ARTIFACT MANIFEST (templates/artifacts/manifest.yaml):
  - plan.md (planning, required)
  - task-checklist.md (planning, required)
  - verification-checklist.md (planning, required)
  - recommended-testing-plan.md (completion, required)
  - post-completion-comments.md (completion, required)

ACTIVE ORCHESTRATION PATTERN: default (orchestration/default.yaml)
  plan_approval_required: false
  auto_merge_on_pass: false

TEMPLATES (read these before creating files):
  templates/issue_templates/default.yaml.j2
  templates/comment_templates/status_change.yaml.j2

SKILL EXAMPLES (read these too):
  .claude/skills/project-manager/examples/issue-fully-formed.yaml
  .claude/skills/project-manager/examples/node-endpoint.yaml
  .claude/skills/project-manager/examples/node-decision.yaml
  .claude/skills/project-manager/examples/session-multi-repo.yaml

VALIDATION GATE (run after every batch of writes):
  agent-project validate --strict --format=json
  Exit 0 = clean, 1 = warnings, 2 = errors
  Always rebuilds graph/index.yaml as a side effect.

ID ALLOCATION:
  - For each new issue: call `agent-project next-key --type issue`
  - For each entity: generate uuid4 and add `uuid:` to frontmatter
  - Do NOT hand-write UUIDs
  - Do NOT manually increment project.yaml.next_issue_number
```

### JSON format

`scaffold-for-creation --format=json` returns the same content as a structured JSON object the agent can parse programmatically. Useful when the agent prefers structured input.

### Implementation

Single CLI command, ~50 lines. Reads `project.yaml`, walks `enums/`, walks `templates/`, looks up `next_issue_number`, lists files in `.claude/skills/project-manager/examples/`. Pure read operation. Extremely fast.

---

## The Project Manager Skill

The PM skill is the most important artifact in the system. More than the CLI, more than the templates, more than the validator. The skill is what tells the agent how to think about a project, what to read first, what to write, when to validate, and what mistakes to avoid.

The skill ships at `templates/skills/project-manager/`, gets copied into the user's project on `init`, and is owned by the project repo afterwards. Projects can extend or override it without forking the package.

### Directory structure

```
.claude/skills/project-manager/
├── SKILL.md                          # entry point — must be ~1 page, scannable
├── references/
│   ├── WORKFLOWS_INITIAL_SCOPING.md  # for the project-kb-pivot case (bulk creation from raw docs)
│   ├── WORKFLOWS_INCREMENTAL_UPDATE.md  # surgical updates to existing entities
│   ├── WORKFLOWS_TRIAGE.md           # processing inbound suggestions/comments
│   ├── WORKFLOWS_REVIEW.md           # PM PR review of project-repo PRs
│   ├── SCHEMA_PROJECT.md             # project.yaml schema + how to read it
│   ├── SCHEMA_ISSUES.md              # issue YAML schema, required body sections
│   ├── SCHEMA_NODES.md               # node YAML schema, types, source fields
│   ├── SCHEMA_SESSIONS.md            # session YAML schema, multi-repo, runtime_state
│   ├── SCHEMA_COMMENTS.md            # comment file schema
│   ├── SCHEMA_ARTIFACTS.md           # session artifacts (plan.md, checklists, etc.)
│   ├── CONCEPT_GRAPH.md              # when to create nodes, how references work, freshness
│   ├── ID_ALLOCATION.md              # UUIDs, sequential keys, next-key, conflict resolution
│   ├── VALIDATION.md                 # the gate: how to run, how to interpret errors, how to fix
│   ├── REFERENCES.md                 # [[node-id]] syntax, when to reference, bi-directional rules
│   ├── COMMIT_CONVENTIONS.md         # what goes in one commit, branch naming, PR titles
│   ├── ANTI_PATTERNS.md              # things agents tend to get wrong, with remedies
│   └── POLICIES.md                   # project-specific rules (placeholder; per-project override)
└── examples/
    ├── issue-fully-formed.yaml       # a complete, validated issue example
    ├── issue-with-references.yaml    # an issue that references multiple nodes
    ├── node-endpoint.yaml            # an endpoint node
    ├── node-model.yaml               # a model node
    ├── node-decision.yaml            # a decision (DEC-xxx) node
    ├── node-config.yaml              # a config (env var) node
    ├── node-contract.yaml            # an API contract node
    ├── session-single-issue.yaml     # a basic session
    ├── session-multi-repo.yaml       # a session spanning multiple repos
    ├── comment-status-change.yaml    # a status_change comment
    ├── orchestration-default.yaml    # a default orchestration pattern
    └── artifacts/                    # example session artifacts
        ├── plan.md
        ├── task-checklist.md
        └── verification-checklist.md
```

### Progressive disclosure

The entry point (`SKILL.md`) is ~1 page and scannable. It points to references that the agent loads on demand. The agent does not read every reference up front — it reads `SKILL.md`, runs `agent-project scaffold-for-creation`, and then loads only the references relevant to the workflow it's running. Reference files are kept short (1-3 pages each), focused on a single topic, and end with a "see also" pointer to related references and worked examples.

### `SKILL.md` entry point (outline)

1. **Purpose**: "You are the project manager for this repo. Your job is to translate intent into concrete, schema-valid project files (issues, nodes, sessions, comments) that other agents can consume."
2. **Two workflows you'll be doing**:
   - Initial scoping → see `references/WORKFLOWS_INITIAL_SCOPING.md`
   - Incremental updates → see `references/WORKFLOWS_INCREMENTAL_UPDATE.md`
3. **Critical: front-load your context first**. Run `agent-project scaffold-for-creation` and read the output before doing anything else.
4. **Write files directly** (don't try to use the CLI to create issues/nodes/sessions; mutation CLI commands are intentionally absent in v0). Read the relevant schema reference and example, then use the `Write` tool.
5. **The validation gate**: run `agent-project validate --strict --format=json` after every batch. Parse the JSON output. Fix every error. Re-run until clean. The validate command also rebuilds the graph cache.
6. **Allocating IDs**:
   - For UUIDs: generate yourself (uuid4) and put in frontmatter.
   - For sequential keys (`SEI-42`, etc.): call `agent-project next-key --type issue` once per new issue. Don't try to read `project.yaml` and increment yourself.
7. **The five mortal sins** (link to `references/ANTI_PATTERNS.md` for full list):
   - Inventing fields not in the schema
   - Forgetting to run `validate` before declaring done
   - Forgetting to allocate the next sequential key via CLI
   - Hand-writing UUIDs (use uuid4)
   - Producing references to entities you didn't create and that don't exist

The entry point ENDS with: "Now read `references/SCHEMA_PROJECT.md` and `references/WORKFLOWS_INITIAL_SCOPING.md` (or `WORKFLOWS_INCREMENTAL_UPDATE.md`) before continuing."

### Reference docs (one-line summaries)

- **`WORKFLOWS_INITIAL_SCOPING.md`** — the workflow for `project-kb-pivot`: read raw planning docs, plan the breakdown into epics/issues/nodes/sessions, allocate IDs, write files, validate, commit.
- **`WORKFLOWS_INCREMENTAL_UPDATE.md`** — surgical updates to existing entities (status change, comment, single new node).
- **`WORKFLOWS_TRIAGE.md`** — processing inbound suggestions and comments into actionable items.
- **`WORKFLOWS_REVIEW.md`** — PM PR review workflow for project-repo PRs.
- **`SCHEMA_PROJECT.md`** — how to read `project.yaml`, what each field means, when to update it.
- **`SCHEMA_ISSUES.md`** — full issue frontmatter, every field with type and constraints, required body sections (Context, Implements, Repo scope, Requirements, Execution constraints, Acceptance criteria, Test plan, Dependencies, Definition of Done).
- **`SCHEMA_NODES.md`** — node types, what each is for, when to create one (the "named bookmark" rule).
- **`SCHEMA_SESSIONS.md`** — session frontmatter, multi-repo `RepoBinding`, runtime state, engagement history.
- **`SCHEMA_COMMENTS.md`** — comment file format, valid types, where comments live in the directory tree.
- **`SCHEMA_ARTIFACTS.md`** — session artifacts (plan, task-checklist, verification-checklist, recommended-testing-plan, post-completion-comments).
- **`CONCEPT_GRAPH.md`** — when to create a node vs inline prose, the `[[node-id]]` syntax, the implicit edge model, freshness, the index cache, `agent-project refs check`.
- **`ID_ALLOCATION.md`** — UUIDs, sequential keys, `next-key`, conflict resolution. The dual-ID system in detail.
- **`VALIDATION.md`** — single command (`agent-project validate --strict --format=json`), output format, how to map error → file → fix, auto-fix behaviour, cache rebuild.
- **`REFERENCES.md`** — `[[node-id]]` resolution, bi-directional consistency, `blocked_by` is canonical (validator computes `blocks`), `related` on nodes is canonical and bi-directional.
- **`COMMIT_CONVENTIONS.md`** — what goes in one commit, branch naming, PR titles.
- **`ANTI_PATTERNS.md`** — common mistakes with worked bad/fixed examples (inventing fields, forgetting timestamps, writing `blocks`, dangling refs, hand-writing UUIDs, trying to use mutation CLI commands that don't exist).
- **`POLICIES.md`** — project-specific rules placeholder; each project overrides.

### Examples (one-line summaries)

- **`issue-fully-formed.yaml`** — a complete, validated issue with every required field and all body sections.
- **`issue-with-references.yaml`** — an issue that references multiple concept nodes via `[[node-id]]`.
- **`node-endpoint.yaml`** — an endpoint node pointing to a route handler (with line range and content hash).
- **`node-model.yaml`** — a model node pointing to a data class.
- **`node-decision.yaml`** — a decision (DEC-xxx) node pointing to a decision document.
- **`node-config.yaml`** — a config node documenting an environment variable.
- **`node-contract.yaml`** — a contract node pointing to an API contract section.
- **`session-single-issue.yaml`** — a basic session for one issue.
- **`session-multi-repo.yaml`** — a session spanning multiple repos with one `RepoBinding` per repo.
- **`comment-status-change.yaml`** — a `status_change` comment file.
- **`orchestration-default.yaml`** — a default orchestration pattern.
- **`artifacts/plan.md`**, **`artifacts/task-checklist.md`**, **`artifacts/verification-checklist.md`** — example session artifacts.

### The canonical truth principle

**The example file is the canonical truth. If a schema doc disagrees with the example, the example wins.** Schema reference docs exist to explain *why* fields exist and *when* to use them, but the literal shape comes from the example. This means improving an example automatically improves the agent's output without anyone having to update the schema docs in lockstep.

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

The order below is reorganised for the agent-driven priority. Build the data layer and validator first; build read commands before any command that mutates state; defer mutation CLI commands to a later release. The whole sequence converges on Step 12 — running the `project-kb-pivot` end-to-end test.

### Step 1: Package scaffold + pyproject + linting
- Create `pyproject.toml`, `Makefile`, `src/agent_project/__init__.py`
- Set up `ruff`, `pytest`, `codespell` config
- Verify `uv sync` and `uv run pytest` work
- Verify `uv run ruff check src/` runs clean on the empty package

### Step 2: Models + parsers + stores + dual ID system
- `models/enums.py` — all StrEnum types (IssueStatus, Priority, Executor, Verifier, NodeType, NodeStatus, etc.)
- `models/project.py` — ProjectConfig (including `repos` with local paths, `graph` settings, `next_issue_number`)
- `models/issue.py` — Issue (with `uuid: UUID = Field(default_factory=uuid.uuid4)` and frontmatter + body)
- `models/node.py` — ConceptNode, NodeSource (with `uuid` field)
- `models/comment.py` — Comment (with `uuid` field)
- `models/session.py` — AgentSession, RepoBinding (with `uuid` field)
- `models/graph.py` — DependencyGraphResult, FreshnessResult, FullGraphResult, GraphIndex
- `core/parser.py` — YAML frontmatter + Markdown body parser/serializer
- `core/reference_parser.py` — `[[node-id]]` extraction from Markdown bodies
- `core/store.py` — File-based CRUD for issues, project config, comments
- `core/node_store.py` — File-based CRUD for concept nodes
- `core/uuid_helpers.py` — UUID generation and validation helpers
- `core/key_allocator.py` — atomic next-key allocation under file lock (used by `next-key` CLI)
- `core/id_generator.py` — sequential `<PREFIX>-<N>` key generation
- `core/enum_loader.py` — dynamic enum loading from `<project>/enums/`
- Unit tests for model validation, serialization round-trips, parsing, reference extraction, store operations, UUID generation, key allocation under concurrent calls

### Step 3: Validator + check catalogue + JSON output + auto-fix
- `core/freshness.py` — content hashing, local + GitHub API fetching, staleness detection
- `core/validator.py` — the validation gate engine with the full check catalogue from "The Validation Gate" section
- JSON output schema implemented with the structure from "The Validation Gate"
- `--fix` auto-fix subset (timestamps, sequence drift, missing UUIDs, bi-directional `related` mismatches, sorted-list normalisation, ID collisions, stale graph cache)
- `core/status.py` — status transition validation
- Unit tests for every check in the catalogue (one test per check) and every auto-fix path

### Step 4: Graph cache (incremental + full rebuild)
- `core/graph_cache.py` — `load_index`, `save_index`, `update_cache_for_file`, `full_rebuild`
- File-lock concurrency (`graph/.index.lock`)
- Validator delegates to graph_cache for the side-effect rebuild
- `core/dependency_graph.py` — port from `dependency_graph.py`, accept `list[Issue]`
- `core/concept_graph.py` — full unified graph builder reading from the cache
- Unit tests for incremental update correctness, full rebuild equivalence, cache invalidation

### Step 5: `init` command (interactive wizard)
- `cli/main.py` — Click root group + global options
- `cli/init.py` — `agent-project init` interactive wizard with `--name`, `--key-prefix`, `--base-branch`, `--repos`, `--no-git`, `--non-interactive`
- Copy the entire `templates/` tree from the package into the new project
- Jinja2 substitution applied to `.j2` files only
- Integration test: init creates valid project, git repo works (or skipped with `--no-git`)

### Step 6: `scaffold-for-creation` command
- `cli/scaffold.py` — `agent-project scaffold-for-creation` with `--format=text|json`
- Output exactly matches the spec in the "scaffold-for-creation" section
- Pure read operation, ~50 lines
- Integration test: output contains all expected sections, JSON output is parseable

### Step 7: `next-key` command
- `cli/next_key.py` — `agent-project next-key --type issue/session --count INT`
- Uses `core/key_allocator.py` for atomic file-locked increment
- Integration test: 10 concurrent invocations produce 10 distinct sequential keys with no gaps or collisions

### Step 8: Read commands
- `cli/validate.py` — `agent-project validate --strict --format=text|json --fix`
- `cli/status.py` — Dashboard with status breakdown, blocked issues, stale refs, critical path
- `cli/graph.py` — `agent-project graph --type deps|concept --format mermaid|dot|json --output --status-filter`
- `cli/refs.py` — `list`, `reverse`, `check`
- `cli/node.py` — `check` subcommand only (read-only freshness check)
- `cli/templates.py` — `list`, `show`
- `cli/enums.py` — `list`, `show`
- `cli/artifacts.py` — `list <session-id>`, `show <session-id> <artifact-name>`
- `output/console.py` — Rich tables, detail views (show `[[references]]` with freshness indicators)
- `output/mermaid.py` — Mermaid diagram generation (deps + concept graph)
- Integration tests for each read command

### Step 9: Templates
- `templates/enums/` — issue_status, priority, executor, verifier, node_type, node_status, session_status, message_type, agent_state, re_engagement_trigger
- `templates/issue_templates/default.yaml.j2`
- `templates/comment_templates/` — status_change, question, completion
- `templates/artifacts/` — manifest.yaml + plan, task-checklist, verification-checklist, recommended-testing-plan, post-completion-comments templates
- `templates/orchestration/default.yaml` (+ `hooks/__init__.py` scaffold)
- `templates/agent_templates/` — backend-coder, frontend-coder, verifier, pm
- `templates/session_templates/default.yaml.j2`
- `templates/project/` — `project.yaml.j2`, `CLAUDE.md.j2`, `gitignore.j2`
- Standards template `templates/standards.md.j2`

### Step 10: PM skill (SKILL.md + references + examples)
- `templates/skills/project-manager/SKILL.md` — entry point (terse, ~1 page)
- `templates/skills/project-manager/references/` — all reference docs from "The Project Manager Skill" section (workflows, schemas, concept graph, ID allocation, validation, references, commit conventions, anti-patterns, policies)
- `templates/skills/project-manager/examples/` — all example files (issues, nodes, sessions, comments, orchestration) + the `artifacts/` subfolder
- Verify the entry point links to the right references and examples
- Verify example files validate cleanly when copied into a fresh project

### Step 11: Other default skills
- `templates/skills/agent-messaging/` — SKILL.md + `references/MESSAGE_TYPES.md`, `EXAMPLES.md`, `ANTI_PATTERNS.md`
- `templates/skills/backend-development/SKILL.md`
- `templates/skills/verification/SKILL.md`

### Step 12: End-to-end verification with `project-kb-pivot`
- Run `agent-project init --name project-kb-pivot --key-prefix PKB --base-branch main --no-git --non-interactive` from inside the existing `project-kb-pivot` directory
- Open Claude Code with the PM skill loaded
- Prompt: "Read all files in `raw_planning/`. Use the `WORKFLOWS_INITIAL_SCOPING` workflow to produce a fully scoped project."
- Verify the agent runs `scaffold-for-creation`, drafts and writes issues/nodes/sessions, runs `validate` until clean, and commits in a single commit
- Iterate on the skill, validator, and templates based on what the verification reveals (this is expected — v0 is done when this test passes cleanly)

---

## Deferred features

The following features are NOT in v0. Each entry includes a rationale for why it was deferred. Most reduce to: "the agent writes files directly; mutation CLI is unnecessary complexity in v0," or "this is a future-facing optimisation that should wait for real-world signal before being designed."

| Feature | Why deferred |
|---------|--------------|
| `agent-project issue {create,update}` (mutation CLI) | Agents write files directly using the `Write` tool. Not needed in v0. Adds complexity and a parallel code path that has to stay in sync with the validator. |
| `agent-project node {create,update}` (mutation CLI) | Same as above. |
| `agent-project session {create,update,re-engage}` (mutation CLI) | Same. `re-engage` becomes relevant only when `agent-containers` exists. |
| `agent-project comment add` (mutation CLI) | Comments are just files. Direct writes work. |
| `agent-project pm review-pr` | The PM PR review concept stays in the docs but the CLI for it is deferred — in v0 the PM agent runs `validate` and inspects PRs directly via files and `gh`. |
| `agent-project orchestrate evaluate` | Orchestration runtime lives in `agent-containers`, not `agent-project`. Deferred until that package is built. |
| `agent-project migrate` (schema migrations) | Premature. Schema is too young to need migrations. Plan to add when v1 makes its first breaking change. |
| Multiple starter templates (`webapp-fullstack`, `python-backend`, `multi-repo-infra`) | Deferred — only the `default` template ships in v0. Stack-specific starters with seed nodes are valuable but require domain research and maintenance. |
| Rust validator | Premature. Python validator with `libyaml` + `msgspec` will handle 5000+ entities in <1s. Profile before reaching for Rust. |
| CI/CD GitHub action for `validate` | Useful but not required for v0. Add when first project hits production. |
| `agent-project init --update` (selective template refresh) | Useful for bringing existing projects up to date when the package adds new templates. Add when first breaking schema change happens. |
| `agent-project node import-from-code` (bulk node creation) | Compelling future feature: scan a code repo, propose nodes for endpoints/models/configs. Requires AST parsing per language. Deferred until v1+. |
| `--watch` mode for `validate` | Nice for a UI/dev loop. UI backend's file watcher covers the same use case once that exists. Defer. |
| Plugin/extension system for custom validators | Premature. Hardcode the v0 check set. |
| Multi-project / workspace mode (manage multiple projects from one CLI invocation) | Defer. Single-project is the only mode in v0. |

---

## Verification

1. **Unit tests**: `uv run pytest tests/unit/ -v` — all model validation, parsing, store, graph, validator, freshness tests pass
2. **Integration tests**: `uv run pytest tests/integration/ -v` — init flow, issue lifecycle, node lifecycle
3. **Manual smoke test** (exercises every v0 CLI command without involving a Claude Code session — entity files are created by hand from templates):
   ```bash
   cd /tmp && agent-project init --name test-project --key-prefix TST --base-branch main --non-interactive
   cd test-project

   # Front-load context (the same command an agent runs first)
   agent-project scaffold-for-creation
   agent-project scaffold-for-creation --format=json

   # Atomic ID allocation
   agent-project next-key --type issue        # returns TST-1
   agent-project next-key --type issue        # returns TST-2

   # Hand-create a couple of issues using the issue template + the keys above.
   # (In normal use, an agent does this via the Write tool. For the smoke test,
   # copy templates/issue_templates/default.yaml.j2 manually and fill it in,
   # writing two files: issues/TST-1.yaml and issues/TST-2.yaml. Make sure each
   # has a UUID in frontmatter and TST-2 has blocked_by: [TST-1].)

   # Hand-create one concept node from .claude/skills/project-manager/examples/node-endpoint.yaml
   # as graph/nodes/auth-endpoint.yaml, and add [[auth-endpoint]] to TST-1's body.

   # The validation gate
   agent-project validate                     # human output
   agent-project validate --strict --format=json
   agent-project validate --fix               # auto-fix trivial issues
   # validate also rebuilds graph/index.yaml as a side effect

   # Read commands
   agent-project status
   agent-project status --format=json
   agent-project graph --type=deps --format=mermaid
   agent-project graph --type=concept --format=mermaid
   agent-project refs list TST-1
   agent-project refs reverse auth-endpoint
   agent-project refs check
   agent-project node check                   # freshness check on all active nodes
   agent-project templates list
   agent-project templates show default
   agent-project enums list
   agent-project enums show issue_status
   agent-project artifacts list <session-id>  # only meaningful after a session exists
   ```
   This smoke test uses only v0 commands. There are no `issue create`, `issue update`, `node create` invocations because those mutation commands are deferred — entity creation goes through direct file writes.
4. **Lint**: `uv run ruff check src/ tests/`
5. **Package install**: `pip install .` from the repo root, then `agent-project --help` works

### `project-kb-pivot` end-to-end test (v0 acceptance criterion)

This is the concrete acceptance test for the v0 system. It exercises the CLI, the validator, the templates, and the PM skill end-to-end through a real Claude Code session.

**Setup**: `/Users/maia/Code/seido/projects/project-kb-pivot/` already exists with:

```
project-kb-pivot/
├── .git/
├── raw_planning/
│   ├── agent-spec.md
│   ├── api-spec.md
│   ├── architecture.md
│   ├── deferred-features.md
│   ├── infra-spec.md
│   ├── local-dev-spec.md
│   ├── pivot-plan.md
│   ├── testing-spec.md
│   ├── transition-spec.md
│   └── ui-spec.md
├── examples/
│   └── graph-overview-example.json
└── issues/   (will be populated by the agent)
```

**Acceptance criteria**:

1. Run `agent-project init --name project-kb-pivot --key-prefix PKB --base-branch main --no-git --non-interactive` from inside the directory (it already has `.git/`). All scaffold files appear.
2. Open a Claude Code session with the `project-manager` skill loaded.
3. Prompt the agent: "Read all files in `raw_planning/`. Use the `WORKFLOWS_INITIAL_SCOPING` workflow to produce a fully scoped project."
4. The agent runs `agent-project scaffold-for-creation`, reads the planning docs, drafts and writes:
   - 15-30 issues in `issues/PKB-*.yaml`, organised by epic
   - 10-25 concept nodes in `graph/nodes/*.yaml` for endpoints, models, decisions, contracts
   - 2-5 sessions in `sessions/*.yaml` representing logical agent groupings
   - Updates to `project.yaml` if the planning docs introduce new repos
5. The agent runs `agent-project validate --strict --format=json`. Exit code is 0.
6. The agent commits the result in a single commit on a branch.
7. A human reviewing the output finds it:
   - Coherent (the issues actually reflect the planning docs)
   - Schema-valid (no errors when re-running `validate`)
   - Well-referenced (issues cite the relevant nodes; nodes cite each other where appropriate)
   - Free of hallucinated fields, made-up enum values, or invented entities

**Until this test passes end-to-end, neither the CLI, the skill, nor the validator is done. This is the integration test for the whole v0 surface.**
