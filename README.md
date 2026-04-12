<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="img/keel_full_black_bg.svg">
    <source media="(prefers-color-scheme: light)" srcset="img/keel_full_white_bg.svg">
    <img src="img/keel_full_transparent.svg" alt="Keel" width="520">
  </picture>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
</p>

> A git-native project tracker where the PM, coders, and verifier are AI agents.

Issues, architecture decisions, contracts, sessions — all YAML files in one
git repo, all cross-referenced, all validated by one 50 ms gate. Designed so
Claude Code (or any agent with file-write tools) can scope, track, and ship
real software projects without drifting from the code.

**[Quickstart](#quickstart)** · **[What it does](#what-it-does)** · **[Slash commands](#slash-commands)** · **[How it works](#how-it-works)** · **[Docs](#docs)**

---

## Quickstart

```bash
pip install keel
keel init my-project
cd my-project
claude
```

Then in Claude Code:

```
/pm-scope Build a knowledge base with nodes and edges. Planning docs in ./planning/.
```

That's it. The agent reads your intent, scopes the project, writes the files,
validates its own work, and hands you a clean project to commit.

`keel init` auto-derives a key prefix from the project name (`my-project-cool` →
`MPC`), defaults to `main` as the base branch, and prompts for anything
non-obvious. Pass `--key-prefix`, `--base-branch`, or `--repos` to override.

## What it does

- **One repo, everything inside.** Issues, concept nodes, sessions, skills, templates, enums — all version-controlled in git. No external DB, no SaaS.
- **Dual ID system.** Canonical UUID + atomic human key (`MP-42`), allocated with `fcntl.flock`. Branch-merge safe.
- **Content-hashed concept graph.** `[[node-id]]` references point at file regions with SHA-256 hashes. Move code → one node updates → every downstream issue catches up. Drift is a validation error.
- **14-check validation gate.** Schema, references, bidirectional consistency, status transitions, freshness, sequence drift. JSON output. Auto-fix subset. ~50 ms on a typical project. Rebuilds the graph cache as a side effect.
- **One-shot context brief.** `keel brief` gives an agent config, enums, templates, skill examples, next IDs, and the validation loop in a single tool-call result. The PM skill calls it automatically — you never have to.
- **Customisable session artifacts.** Plans, task checklists, verification checklists, testing plans, post-completion comments — per-project manifest, enforced by the validator.
- **Progressive-disclosure PM skill.** 33 reference files and canonical examples ship into every `init`. The agent reads the example, not the schema doc.

## Demo

```text
$ keel validate --strict
{
  "exit_code": 0,
  "errors": [],
  "warnings": [],
  "fixed": [],
  "cache_rebuilt": true,
  "duration_ms": 47
}

$ keel status --format=rich
my-project (MP)
  Issues: 23  (backlog=12, todo=8, in_progress=3)
  Concept nodes: 17 active, 2 stale
  Sessions: 4  (2 completed, 1 in_progress, 1 waiting_for_review)
  Critical path: MP-1 → MP-7 → MP-12 → MP-18  (length 4)

$ keel uuid --count 3
# Entity 1
a1b2c3d4-e5f6-4789-abcd-ef0123456789
# Entity 2
f9e8d7c6-b5a4-4321-8765-432109876543
# Entity 3
12345678-90ab-4cde-8f01-234567890abc
```

## How it works

Four principles. Each one is a deliberate choice.

**1. The project repo is the single source of truth.** Nothing lives in Linear, Notion, or a Google Doc. Clone the repo and you have the whole project.

**2. Agents are the primary users.** The CLI is intentionally minimal — read, validate, atomic ID allocation. Agents create issues and nodes by writing files directly with their `Write` tool, then run the validator.

**3. The concept graph is coherence.** Instead of prose like "the auth endpoint," issues reference `[[auth-token-endpoint]]` — a node file pointing at a specific file and line range with a stored content hash. When the code moves, one file updates. Stale hashes surface as validator errors.

**4. Validation is the gate.** Every agent loop ends with `keel validate --strict --format=json`. The same command rebuilds the graph cache incrementally. The loop is: write files → validate → fix → validate → commit.

**Why in-repo.** Project artifacts — decisions, contracts, issue history — have long tails. You need to know why a decision was made three years from now. External SaaS trackers lose that history when companies migrate tools, pivot pricing, or shut down. Keel issues are git commits: readable with `cat` in 20 years, diffable with `git log`, portable with `git clone`. The project's history is as durable as its code.

## Slash commands

After `keel init`, every project ships with `/pm-*` slash commands at
`.claude/commands/`. Type `/pm` in Claude Code to see them all at once.

| Command | What it does |
|---|---|
| `/pm-scope <intent>` | Scope a new project from your intent and optional planning docs |
| `/pm-update <change>` | Apply a surgical change (status, comment, new node, session update) |
| `/pm-triage` | Process inbound suggestions, comments, and agent messages |
| `/pm-review <PR>` | Review a PR against the project repo for quality and completeness |
| `/pm-status` | PM-flavoured project summary with next-step recommendations |
| `/pm-graph` | Analyse the dependency graph: critical path, parallelizable work, cycles |
| `/pm-validate` | Run the validator, interpret errors, propose and apply fixes |
| `/pm-agenda` | Interpreted summary of everything in flight with recommendations |
| `/pm-plan` | Preview what init would produce, with interpretation |
| `/pm-handoff <issue>` | Create a session for an issue and hand off to a coding agent |
| `/pm-rescope <intent>` | Expand an existing project with new scope |
| `/pm-close <issue>` | Mark an issue done and write a closing comment |

Each slash command loads the project-manager skill, reads current state via
`keel brief`, then executes the relevant workflow.

## Commands

```text
keel init                     Bootstrap a project with templates + skills
keel next-key                 Atomic ID/key allocation (fcntl.flock)
keel validate                 14-check gate  (--strict, --fix, --format=json)
keel status                   Dashboard: issues, nodes, sessions, critical path
keel graph                    Render dependency or concept graph (mermaid/dot/json)
keel refs                     Inspect references to a node or issue
keel node                     List, inspect, freshness-check concept nodes
keel templates                List and instantiate Jinja2 templates
keel enums                    List active enum values
keel artifacts                List session artifact manifest
keel brief                    Dump project context (agents use this internally)
keel agenda                   Aggregated view of everything in flight
keel plan                     Preview what init would produce (dry-run)
keel uuid                     Generate RFC 4122 UUID4 values (--count N)
keel refresh                  Rebuild the graph cache from filesystem
keel view                     Serve a read-only HTML project viewer
keel completion <shell>       Print bash/zsh/fish tab completion install snippet
```

All commands output JSON by default (agent-first). Add `--format=text`
or `--format=rich` for human-readable output.

Run `keel --help` or `keel <cmd> --help` for details.

## Project layout

After `keel init`:

```text
my-project/
├── project.yaml              # one config file
├── issues/MP-*.yaml          # issue files (one per entity)
├── graph/
│   ├── nodes/*.yaml          # concept nodes
│   └── index.yaml            # derived cache (rebuildable)
├── sessions/sess-*/          # one folder per agent session
│   ├── session.yaml
│   ├── plan.md
│   ├── task-checklist.md
│   ├── verification-checklist.md
│   ├── recommended-testing-plan.md
│   └── post-completion-comments.md
├── enums/*.yaml              # customisable per project
├── orchestration/default.yaml
├── templates/                # Jinja2 templates the agent renders
└── .claude/skills/           # progressive-disclosure agent guidance
    ├── project-manager/
    ├── backend-development/
    ├── frontend-development/
    └── verification/
```

---

<details>
<summary><b>Why drift matters</b> — the problem this solves</summary>

You can't run a real software project on a stack of LLM agents yet, and the reason is drift.

- **Your issue tracker drifts from your code.** You write "the auth endpoint in the backend" today; six weeks later that endpoint moves and the issue text doesn't. The next agent builds against stale information.
- **Your context is scattered.** The issue is in Linear, the decision is in Notion, the API contract is in a Google Doc, the schema is in a Terraform module. An agent piecing those together burns half its tokens on reconciliation.
- **You can't run multiple coding agents in parallel without a coordinator.** Each needs a branch, an issue key, an awareness of who owns what. Without atomic key allocation, they stomp on each other.
- **Drift is a tax on every future invocation.** Mechanical search-and-replace across docs, issues, code, and schemas is exactly what LLMs are bad at. Partial reconciliations leave the next agent with more drift to chase.

`keel` fixes this by putting everything in one git repo with cross-referenced YAML, content-hashed concept nodes, and a 14-check validator that catches drift before the next agent reads it.

</details>

<details>
<summary><b>Under the hood</b> — dual IDs, graph cache, freshness, orchestration</summary>

**Dual IDs.** Every entity has both a canonical `uuid4` (agent-generated, never changes) and a human key like `MP-42` (allocated atomically by `next-key` under `fcntl.flock`). Key collisions across branches are detected by the validator and resolved via the UUID, so references don't break.

**Concept graph with content hashing.** A concept node points at a region of a file in a repo:

```yaml
source:
  repo: myorg/backend
  path: src/api/routes/auth.py
  lines: [45, 82]
  branch: main
  content_hash: "sha256:e2c5a..."
```

`keel node check` fetches the current content (local clone preferred, `gh api` fallback) and compares SHA-256 hashes. Three outcomes: `FRESH`, `STALE`, `SOURCE_MISSING`. Stale nodes become validator errors.

**Graph cache.** `graph/index.yaml` is an incremental cache of all edges, rebuilt under `fcntl.flock`. `validate` calls `ensure_fresh` which picks between incremental update and full rebuild based on the current state.

**Auto-fix subset.** `validate --fix` repairs: missing timestamps (from file mtime), drifted `next_issue_number`, missing UUIDs, bidirectional `related` mismatches, label/list normalisation, basic ID collision renames. Everything else is on the agent.

**Orchestration patterns.** Declarative YAML rules for when humans approve, when the PM auto-acts, when sessions merge on pass:

```yaml
events:
  on_session_complete:
    - condition: "verification.passed"
      action: "merge_branch"
    - condition: "verification.failed"
      action: "request_human_review"
```

Per-project defaults in `orchestration/default.yaml`; per-session overrides in the session folder. The runtime that consumes them (see `docs/agent-containers.md`) is configured *by* the project repo, not the other way round.

**The PM skill.** `.claude/skills/project-manager/` ships into every `init` with 17 reference docs (workflows, schemas, validation codes, anti-patterns) and 13 canonical example files. When the agent is confused it reads the example. When the example is wrong the validator catches it.

</details>

<details>
<summary><b>Worked example</b> — scoping from raw planning docs</summary>

1. `keel init my-project` creates the project with 73 templates, 43 skill files, 10 slash commands, 11 enums. Auto-derives the key prefix from the name (`my-project` → `MP`).
2. You open Claude Code in `my-project/` and type: `/pm-scope Build a knowledge base. Planning docs in ./raw_planning/.`
3. The PM skill auto-loads. It calls `keel brief` to read project state, then reads `raw_planning/*.md`.
4. The agent calls `keel next-key --type issue` 20 times, writes 20 issue YAML files into `issues/`, writes 15 concept nodes into `graph/nodes/`, writes 3 session folders into `sessions/`.
5. It runs `keel validate --strict --format=json`, parses the JSON, fixes any `ref/dangling`, `body/missing_heading`, or `status/unreachable` errors, re-runs.
6. Clean. The agent commits the result. You `keel status` and see a connected dependency graph with a critical path.

Everything is in git. Every reference resolves. Every concept node's content hash is current. The next agent that picks up a ticket has the full picture from one clone.

</details>

---

## Status

**v0.** 448 tests pass. The validation gate is stable. The PM skill and 10 `/pm-*` slash commands ship into every initialised project. APIs may change before v1.

**Not in v0:** web UI, managed cloud version, the agent execution runtime itself. Those are tracked in `docs/agent-containers.md` and `docs/keel-ui.md`.

## Docs

- Design: `docs/keel-plan.md`
- Agent execution runtime: `docs/agent-containers.md`
- Web dashboard: `docs/keel-ui.md`
- Platform plan: `docs/overarching-plan.md`

## License

MIT. See `LICENSE`.
