# Agent Projects

> Git-native project management with a concept graph, designed for AI agents.

`agent-project` is a Python library and CLI for running software projects
where the project manager, the coders, and the verifier are all AI
agents — and the project itself is just a git repository.

It is the project layer for [seido](https://github.com/SeidoAI), but it
works on its own. If you want a Claude Code session to take a stack of
raw planning docs and produce a fully-scoped project that humans and
agents can actually work from, this is the tool.

---

## The problem

You can't run a real software project on a stack of LLM agents yet, and
the reason is drift.

**Your issue tracker drifts from your code.** You write an issue today
that says "the auth endpoint in the backend." Six weeks later that
endpoint moves, gets renamed, and grows a new parameter. The issue text
doesn't move with it. A new agent picks up a downstream ticket, builds
against stale information, and the bug surfaces two PRs later when
something else breaks.

**Your context is scattered across five systems.** The issue is in
Linear, the architecture decision is in Notion, the API contract is in
a Google Doc, the schema is in a Terraform module on GitHub, and the
deployment runbook is in Confluence. An agent that needs all of them
has to piece the picture together from five sources that disagree with
each other. Half the agent's tokens go to reconciliation instead of
work.

**You can't run multiple coding agents in parallel without a coordinator.**
Each one needs its own branch, its own issue key, its own awareness of
who else is touching which file. Without a central authority that hands
out keys atomically and tracks who owns what, agents stomp on each
other constantly.

**Drift is a tax on every future agent invocation.** Reconciling drift
means mechanical search-and-replace across docs, issues, code, tests,
schema files, and infrastructure. LLMs are bad at this. They miss
instances. They update some references but not others. They burn tokens
re-reading the same files looking for one more occurrence. The result
is partial — and a partial reconciliation means the *next* agent has
even more drift to chase.

This is why agent-driven development looks great in demos and falls
apart on real projects. The execution layer (Claude Code, Cursor,
Aider) is good now. The coordination layer is the gap.

---

## The philosophy

Four principles. Each one is a deliberate choice we made and will
defend.

### 1. The project repo is the single source of truth

Issues, concept nodes, sessions, comments, orchestration patterns,
skills, templates, and enums all live as version-controlled files in
**one** git repository. There is no external database. There is no
SaaS dependency. There is nothing to keep in sync, because there is
only one place.

```
my-project/
├── project.yaml              # the one config
├── issues/
│   ├── MP-1.yaml
│   ├── MP-2.yaml
│   └── ...
├── graph/
│   ├── nodes/                # concept nodes (decisions, contracts, models)
│   └── index.yaml            # derived cache, rebuildable from sources
├── sessions/                 # one folder per agent session
│   └── sess-001/
│       ├── session.yaml
│       ├── plan.md
│       ├── task-checklist.md
│       └── verification-checklist.md
├── enums/                    # customisable per project
│   ├── issue_status.yaml
│   ├── priority.yaml
│   └── ...
├── orchestration/            # event-driven workflow rules
│   └── default.yaml
├── templates/                # Jinja2 templates the agent renders
└── .claude/skills/           # progressive-disclosure agent guidance
    ├── project-manager/
    ├── backend-development/
    ├── frontend-development/
    └── verification/
```

Want to understand the whole project? Clone the repo. Want to roll back
yesterday's bad scoping decision? `git revert`. Want to see who wrote
which issue? `git blame`.

### 2. Agents are the primary users

The CLI is intentionally minimal:

```
agent-project init                  Bootstrap a new project
agent-project scaffold-for-creation Dump everything an agent needs
agent-project next-key              Atomic ID/key allocation
agent-project validate              The validation gate (14 checks)
agent-project status                Dashboard
agent-project graph                 Render the dependency or concept graph
agent-project refs / node           Inspect references and nodes
agent-project templates / enums     List the customisable bits
```

Notice what is **not** there: no `create-issue`, no `add-comment`, no
`update-status`. Those would be CLI ceremony that an agent doesn't
need. The agent uses its `Write` tool to create the file directly,
then runs `validate` to confirm the file is correct.

The project ships with a `project-manager` skill — 33 files of
progressive-disclosure guidance — that teaches Claude Code (or any
similar agent) the schemas, workflows, and anti-patterns. The skill is
the manual. The validator is the gate. The agent does the work.

### 3. The concept graph is coherence

When an issue says "the JWT auth endpoint," it does not say it in
prose. It says it as a reference:

```yaml
---
id: MP-42
title: Add refresh-token rotation to auth
---
## Context

The current implementation in [[auth-token-endpoint]] issues a JWT
with a 1h lifetime. We need to add a refresh-token rotation flow per
[[dec-005-refresh-rotation]].
```

`[[auth-token-endpoint]]` and `[[dec-005-refresh-rotation]]` are
**concept nodes** — small YAML files in `graph/nodes/` that point to
the canonical definition of a thing:

```yaml
---
id: auth-token-endpoint
type: endpoint
status: active
title: POST /auth/token
source:
  repo: SeidoAI/web-app-backend
  path: src/api/routes/auth.py
  lines: [45, 82]
  content_hash: "sha256:e2c5a..."
---
The JWT token issuance endpoint. Validates email + password, returns
a signed JWT plus a refresh token...
```

Three things matter about this design:

- **One file owns the definition.** When the endpoint moves to
  `lines: [50, 88]`, you update one node file, not 17 issues that
  reference it.
- **The content hash detects drift automatically.** Run
  `agent-project node check`, the validator fetches the current file
  content and compares its SHA-256 against the stored hash. Stale
  nodes are flagged before they poison downstream work.
- **The graph is queryable.** `agent-project graph --type concept`
  renders the full graph as Mermaid, DOT, or JSON. `agent-project refs
  --node auth-token-endpoint` lists every issue, session, and node
  that references it.

### 4. Validation is the gate

Every agent loop ends with one command:

```
agent-project validate --strict --format=json
```

That command runs 14 checks across every file in the project:

1. Schema — every YAML parses and matches its Pydantic model
2. UUID — every entity has a `uuid4`
3. ID format — issue keys match `<PREFIX>-<N>`, node ids are slugged
4. Enum values — every status/priority/etc. is in the active enum
5. Reference integrity — every `[[node]]`, `blocked_by`, `parent`,
   `repo`, and `agent` reference resolves
6. Bidirectional `related` — node-to-node `related` is symmetric
7. Issue body structure — required Markdown sections present
8. Status transitions — every issue's status is reachable from start
9. Concept node freshness — content hashes still match the live source
10. Artifact presence — completed sessions have all required artifacts
11. ID collisions — no two files claim the same id
12. Sequence drift — `next_issue_number` is past the highest existing
13. Timestamps — parseable, set
14. Comment provenance — author/type/created_at present and valid

It exits 0, 1, or 2 — clean, warnings, errors. With `--format=json`
the agent gets a machine-parseable report. With `--fix` a defined
subset of issues (timestamps, UUIDs, sequence drift, bidirectional
mismatches) get repaired automatically. As a side effect, the same
command rebuilds the graph cache (`graph/index.yaml`) incrementally,
so the next read is O(1).

The agent loop is: write files → validate → fix → validate → commit.

---

## What it feels like

Here's the actual end-to-end loop, with real terminal output.

**1. Bootstrap an empty project.**

```
$ agent-project init my-project --name my-project --key-prefix MP --base-branch main
Initialized project 'my-project' (key prefix: MP)
  → 73 templates, 43 skill files, 11 enums
  → next-key: MP-1
```

**2. Load the context for a Claude Code session.**

```
$ agent-project scaffold-for-creation
PROJECT: my-project (MP)
Base branch: main

NEXT IDS:
  next issue key: MP-1
  next session key: sess-001

ACTIVE ENUMS
  issue_status: backlog, todo, in_progress, blocked, in_review, done, cancelled
  priority: critical, high, medium, low
  ...

ACTIVE ARTIFACT MANIFEST
  plan.md (planning, required)
  task-checklist.md (planning, required)
  verification-checklist.md (planning, required)
  recommended-testing-plan.md (planning, required)
  post-completion-comments.md (completion, required)

TEMPLATES
  issue_templates/default.yaml.j2
  comment_templates/{completion,question,status_change}.yaml.j2
  session_templates/default.yaml.j2

SKILL EXAMPLES
  examples/issue-fully-formed.yaml
  examples/node-endpoint.yaml
  examples/session-multi-repo.yaml
  ...

VALIDATION GATE
  Run after every batch of file writes:
    agent-project validate --strict --format=json
  Exit 0 = clean. Anything else, fix and re-run.

ID ALLOCATION
  Allocate the next issue key atomically:
    agent-project next-key --type issue
  Generate UUIDs in your code (uuid4). Do NOT hand-write UUIDs.
```

**3. Point a Claude Code session at the directory.** Load the
project-manager skill. Hand it raw planning docs. Tell it to scope.

The agent reads the docs. It calls `agent-project next-key --type issue`
20 times. It writes 20 issue YAML files into `issues/`. It writes 15
concept node files into `graph/nodes/`. It writes 3 session folders
under `sessions/`. It runs `validate --strict --format=json`.

```
{
  "exit_code": 2,
  "errors": [
    {
      "code": "ref/dangling",
      "severity": "error",
      "file": "issues/MP-12.yaml",
      "field": "blocked_by[0]",
      "message": "MP-12 references non-existent issue MP-99",
      "fix_hint": "Either create MP-99 or remove the blocked_by entry."
    },
    ...
  ]
}
```

The agent fixes them. Re-runs. Exits 0. Commits the result.

**4. Inspect the result as a human.**

```
$ agent-project status
my-project (MP)
  Total issues: 20
  By status: backlog=15, todo=5
  By priority: critical=2, high=8, medium=8, low=2
  Concept nodes: 15
  Sessions: 3
  Critical path: MP-1 → MP-7 → MP-12 → MP-18 → MP-20 (length 5)
```

```
$ agent-project graph --type concept --format mermaid > graph.mmd
```

Open `graph.mmd` in any Mermaid renderer; you see the full project as
a connected graph of issues, nodes, and edges.

Everything is in git. Everything cross-references everything. The next
agent that picks up a ticket has the full picture from one read.

---

## The cool stuff

Pieces of the design that took real thought and that we are quietly
proud of.

### Dual ID system

Every entity has two IDs:

- A canonical **UUID4** that is generated once and never changes. The
  agent generates it in code via `uuid.uuid4()`. References between
  files use this when they need to be branch-merge-safe.
- A human-readable **key** like `MP-42`. The key is allocated
  atomically by `agent-project next-key`, which uses an `fcntl.flock`
  on a counter file in the project. Two parallel branches can both
  ask for the next key without collision.

If two branches do collide on a key (e.g. both grab `MP-42` because
neither saw the other's commit), the validator detects the collision
and the agent renames one. The references update because they go
through the UUID, not the key.

### The concept graph with content hashing

A concept node points at a region of a file in another repo:

```yaml
source:
  repo: SeidoAI/web-app-backend
  path: src/api/routes/auth.py
  lines: [45, 82]
  branch: main
  content_hash: "sha256:e2c5a..."
```

`agent-project node check` fetches the current content (from a local
clone if you have one, otherwise via `gh api`) and compares the SHA-256.
Three outcomes: `FRESH`, `STALE`, `SOURCE_MISSING`. Stale nodes
become validator errors before they propagate to downstream issues.

The same mechanism makes the concept graph queryable across the
project. Move a function and the validator tells you about every
issue and session that thought it lived at the old location.

### `scaffold-for-creation`

One CLI command dumps everything an agent needs to do useful work:

- Project name, key prefix, base branch, repos
- All active enums with their values
- The artifact manifest (what files each session must produce)
- The orchestration pattern (when humans are notified, how PRs land)
- Available templates and skill examples
- Next issue key and next session key
- The exact validation gate command and ID-allocation rules

All in one tool-call result, formatted for either text or JSON output.
The agent reads it once at the start of a session and stops asking
"what's the schema again?"

### The validation gate

Every check in the catalogue is independent and runs in parallel-friendly
fashion. The whole gate finishes in ~50ms on a typical project. The
output is structured: each finding has a code, a severity, a file, a
line, a field, and a `fix_hint`. The agent parses the JSON, fixes the
findings, re-runs.

A defined subset of issues are auto-fixable with `--fix`:

- Missing `created_at` / `updated_at` → fill from file mtime
- Drifted `next_issue_number` → bump
- Missing `uuid` → generate uuid4
- Bidirectional `related` mismatch → add the missing side
- Sorted-list normalisation (labels, related)
- Basic ID collision rename

The auto-fixes are deliberately conservative. The agent does the rest.

### Session artifacts

Every session produces a fixed set of markdown files:

- `plan.md` — what we're going to do, why
- `task-checklist.md` — the breakdown the coder works through
- `verification-checklist.md` — what the verifier checks
- `recommended-testing-plan.md` — how the QA agent tests
- `post-completion-comments.md` — what gets posted on merge

All markdown. All in git. All human-readable. The artifact manifest is
**customisable per project** — add your own artifacts, mark them
required, mark them as approval gates, scope them to planning vs
completion phase. The validator enforces presence based on session
status.

### Orchestration patterns

Declarative YAML rules govern when humans approve, when the PM
auto-acts, and when sessions merge on pass:

```yaml
events:
  on_session_complete:
    - condition: "verification.passed"
      action: "merge_branch"
    - condition: "verification.failed"
      action: "request_human_review"
  on_pr_review_requested:
    - action: "notify_pm_agent"
```

Per-project defaults live in `orchestration/default.yaml`. Per-session
overrides drop into the session folder. The runtime that consumes them
(see `docs/agent-containers.md`) is configured *by* the project repo,
not the other way round.

### The PM skill

`.claude/skills/project-manager/` ships into every initialized project.
33 files of progressive-disclosure guidance:

- `SKILL.md` — a one-page entry point with the loop
- `references/WORKFLOWS_INITIAL_SCOPING.md` — how to scope from raw planning docs
- `references/WORKFLOWS_INCREMENTAL_UPDATE.md` — how to add a new issue mid-project
- `references/WORKFLOWS_TRIAGE.md` — how to handle a flood of incoming work
- `references/CONCEPT_GRAPH.md` — how to design nodes and references
- `references/SCHEMA_*.md` — schema docs for issues, nodes, sessions, comments, projects
- `references/VALIDATION.md` — the catalogue of validator codes and how to fix each
- `references/ANTI_PATTERNS.md` — what *not* to do, with examples
- `examples/*.yaml` — canonical example files for every entity type

The principle: a canonical example file beats a paragraph of schema
documentation every time. When the agent gets confused, it reads the
example. When the example is wrong, the validator catches it.

---

## Quickstart

### Install

```
pip install agent-project
```

Or with uv:

```
uv tool install agent-project
```

### Bootstrap a project

```
agent-project init my-project \
  --name my-project \
  --key-prefix MP \
  --base-branch main \
  --description "What this project is for" \
  --repos "MyOrg/backend,MyOrg/frontend"
cd my-project
```

You now have a fully-formed project with templates, skills, and an
empty `issues/` directory.

### Load the agent context

```
agent-project scaffold-for-creation
```

Paste the output into a Claude Code session. Tell the agent: "You are
the project manager. Load `.claude/skills/project-manager/SKILL.md`.
Read these raw planning docs and scope the project."

### Validate

After the agent has produced files:

```
agent-project validate --strict --format=json
```

If it exits 0, commit the result. If it exits non-zero, the agent has
the JSON error report and knows what to fix.

### Set up shell completion (optional)

```
agent-project completion zsh >> ~/.zshrc       # zsh
agent-project completion bash                  # bash (prints install snippet)
agent-project completion fish                  # fish
```

### Set up the pre-commit hook (development only)

```
make pre-commit-install
```

---

## Status

**v0** — the implementation described in `docs/agent-projects-plan.md`
is complete. 360+ tests pass. The validation gate is stable. The PM
skill ships into every initialized project.

What is **not** in v0:

- The Web UI (a separate project, see `docs/agent-projects-ui.md`)
- The agent runtime (a separate project, see `docs/agent-containers.md`)
- A managed cloud version

What v0 *is* good for: running the project-manager loop locally with
Claude Code or any similar agent that has file-write tools, then
committing the result to git.

---

## Links

- The full design document: `docs/agent-projects-plan.md`
- Agent containers (the execution runtime): `docs/agent-containers.md`
- Agent projects UI (the dashboard): `docs/agent-projects-ui.md`
- The overarching platform plan: `docs/overarching-plan.md`

---

## License

MIT. See `LICENSE`.
