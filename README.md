<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)"  srcset="https://raw.githubusercontent.com/SeidoAI/tripwire/main/img/mark-accent-cream.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/SeidoAI/tripwire/main/img/mark-accent.svg">
    <img alt="tripwire" src="https://raw.githubusercontent.com/SeidoAI/tripwire/main/img/mark-accent.svg" width="360">
  </picture>
</p>

<p align="center">
  <a href="https://github.com/SeidoAI/tripwire/actions/workflows/ci.yml"><img src="https://github.com/SeidoAI/tripwire/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
  <a href="https://pypi.org/project/tripwire-pm/"><img src="https://img.shields.io/pypi/v/tripwire-pm" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
</p>

> A git-native project-management framework for AI software teams. Tripwires catch agent drift from workflow requirements; a concept graph as ground truth aligns agents.

**[Quickstart](#quickstart)** · **[What you get](#what-you-get)** · **[Principles](#principles)** · **[Lifecycle](#v07-lifecycle-flow)** · **[Commands](#commands)** · **[Slash commands](#slash-commands)**

---

## Quickstart

```bash
pip install tripwire-pm
tw init my-project
cd my-project
claude
```

Then in Claude Code:

```
/pm-scope Build a knowledge base with nodes and edges. Planning docs in ./plans/.
```

`tw init` creates issue keys from your project name (`my-project-cool` → `MPC`).

Web dashboard: `tw ui`.

### Minimal install

```bash
pip install "tripwire-pm[projects]"
```

## What you get

- **One repo, everything inside.** Issues, nodes, sessions, skills, templates — all git. No DB, no SaaS.
- **Dual IDs.** UUID + atomic human key (`MP-42`). Branch-merge safe.
- **Content-hashed concept graph.** `[[node-id]]` references pin to file regions with SHA-256. Move the code, the graph catches up.
- **23-check validator.** ~50 ms. JSON by default. Rebuilds the graph cache as it runs.
- **Session lifecycle.** `queue → spawn → monitor → review → complete`. Each stage gates the next.
- **Insights capture.** Sessions propose graph updates in `insights.yaml`. PM reviews at close-out; knowledge compounds.
- **Canonical YAML spawn config.** One place decides model, effort, budget, prompt. Override what matters.
- **PM skill.** 20 reference docs and 14 examples ship with every project. The agent reads the example, not the schema.

## Principles

### 1. The graph is the synchronization layer that makes drift impossible

AI-driven work across issue trackers, docs, code comments, PR
descriptions, and ADRs produces redundant descriptions of the same
concept. Every copy drifts. Tripwire's concept graph is the single
source of truth for every domain concept the project models — issues,
PRs, code comments, READMEs, cross-repo workspace nodes reference
nodes by pointer (`[[node-id]]`). There is one place to update and
no alternative location for the same information to live.

### 2. Deviation is expected; tripwires catch what prevention can't

Agents drift during execution. Prevention cripples autonomy; tolerance
produces wrong PRs. Tripwire designs for the failure: validators emit
warnings into the agent's most recent context so they have a higher
probability of being addressed before the agent proceeds. Tripwires
are sensors, not locks — lightweight enough to preserve autonomy,
explicit enough to redirect cleanly.

### 3. Config over convention, with opinions

Tripwire ships opinionated defaults in YAML — how sessions should
spawn, what artifacts are required, what statuses mean, what the agent
spawn prompt should say. Projects override where they legitimately
differ. Tripwire is *not* configurable about validation-as-a-gate,
artifacts-as-evidence, single-agent-sessions, or the graph-as-canon
— softening those breaks the mechanism.

### 4. Work compounds; sessions are knowledge-producing events

A session's deliverable is the PR **plus** the updated concept nodes,
developer notes, and verified notes. A session that ships code without
updating what the project knows about itself has made the project
worse — the next agent inherits more confusion, not less. Status
advancement is gated on artifact production because artifacts are
where the knowledge lives.

### 5. Decomposition is a first-class product

Execution quality is bounded by framing quality. PM work — scoping,
plan writing, session layout, acceptance criteria, dependency DAGs —
is the highest-leverage work in the project, and the decomposition
itself is a deliverable that deserves quality, review, and iteration.
This is why tripwire has more PM-facing features than execution-facing
ones.

## How it works

**The graph is coherence.** Issues reference `[[auth-token-endpoint]]`, not prose. Move the code, update the node, every reference catches up. Drift is a validator error.

**Validation is the gate.** Every loop ends with `tw validate --strict`. Write → validate → fix → validate → commit.

**Sessions are knowledge-producing events.** A session ends at `tw session complete`, which gates on PR merged, artifacts present, and review exit-code ≤ 1. Proposed graph updates get PM-reviewed before close-out.

**The project ships its own instruction set.** `tw init` ships the PM skill, slash commands, and validation loop into the repo. Fork the project, fork the methodology.

## v0.7 lifecycle flow

```
plan ──► queue ──► spawn ──► execute ──► monitor ──► review ──► complete
  │        │         │          │           │          │          │
  │        │         │          │           │          │          └─ gates on PR merged
  │        │         │          │           │          │             + artifacts present
  │        │         │          │           │          │             + review exit ≤ 1
  │        │         │          │           │          │             closes issues, cleans worktree,
  │        │         │          │           │          │             reviews insights
  │        │         │          │           │          └─ writes verified.md + review.json
  │        │         │          │           └─ one-shot / looped snapshot
  │        │         │          │              (turn, cost, latest tool, PR)
  │        │         │          └─ writes developer.md + task-checklist.md,
  │        │         │             opens PR
  │        │         └─ creates worktree + launches `claude -p` with resolved spawn config
  │        └─ readiness check: plan.md + verification-checklist.md present, blockers done
  └─ plan.md + verification-checklist.md written during scoping
```

Each step is a CLI verb and a matching `/pm-session-*` slash command. The verbs are mechanical; the slash commands add PM judgment.

## Commands

```text
tw init              Bootstrap a project
tw brief             Dump project context
tw validate          23-check gate
tw status            Dashboard
tw agenda            In-flight view
tw plan              Dry-run init
tw next-key          Atomic key allocation
tw uuid              Generate UUID4

tw session …         Session lifecycle
tw issue …           Per-issue artifacts
tw workspace …       Multi-project workspace
tw ci install        Project CI workflow

tw graph             Render dependency or concept graph
tw refs              Inspect references
tw node              Freshness-check nodes
tw templates         List and instantiate templates
tw enums             List active enum values
tw artifacts         List artifact manifest
tw refresh           Rebuild the graph cache
tw lint              Per-stage lint rules
tw ui                Web dashboard
tw view              HTML project viewer
tw completion <sh>   Shell tab-completion
```

Default output is JSON; add `--format=text` or `--format=rich` for humans. Run `tw --help` for details.

## Slash commands

After `tw init`, `/pm-*` commands ship at `.claude/commands/`. Type `/pm` in Claude Code to list them.

### Scoping
| Command | Args | What it does |
|---|---|---|
| `/pm-scope` | `<intent>` | Scope a new project |
| `/pm-rescope` | `<intent>` | Expand existing scope |
| `/pm-triage` | — | Process inbound suggestions |
| `/pm-edit` | `<entity> <change>` | Surgical edit |

### Sessions
| Command | Args | What it does |
|---|---|---|
| `/pm-session-create` | `<session-id>` | Create session YAML |
| `/pm-session-queue` | `<session-id>` | Readiness check; queue |
| `/pm-session-spawn` | `<session-id>` | Worktree + launch `claude -p` |
| `/pm-session-check` | `<session-id>` | Readiness punch list |
| `/pm-session-agenda` | — | Session dependency DAG |
| `/pm-session-progress` | `[--focus ID]` | Task-checklist rollup |
| `/pm-session-monitor` | `[ids...]` | Runtime observation |
| `/pm-session-review` | `<session-id>` | Review PR; write `verified.md` |
| `/pm-session-complete` | `<session-id>` | Close-out gates |

### Issues
| Command | Args | What it does |
|---|---|---|
| `/pm-issue-close` | `<issue-key>` | Mark done; write close comment |
| `/pm-issue-artifact` | `<key> <name>` | Create or update issue artifact |

### Project / workspace
| Command | Args | What it does |
|---|---|---|
| `/pm-project-create` | `<name>` | Bootstrap project under workspace |
| `/pm-project-sync` | — | Pull canonical nodes from workspace |

### Interpretive
| Command | Args | What it does |
|---|---|---|
| `/pm-status` | — | Summary + next-step recommendations |
| `/pm-agenda` | — | In-flight summary |
| `/pm-graph` | — | Critical path, parallel work, cycles |
| `/pm-review` | `<PR>` | Review a PR |
| `/pm-validate` | — | Run validator; interpret and fix |
| `/pm-lint` | `<stage>` | Per-stage lint rules |

## Project layout

After `tw init`:

```text
my-project/
├── project.yaml                     # project config
├── .tripwire/
│   ├── commands/                    # slash-command overrides
│   └── spawn/                       # spawn-config overrides
├── enums/*.yaml                     # project-level enum overrides
├── issues/<KEY>/
│   ├── issue.yaml
│   ├── developer.md                 # written at in_review
│   ├── verified.md                  # written at verified
│   └── comments/
├── nodes/*.yaml                     # concept graph
├── sessions/<id>/
│   ├── session.yaml
│   ├── handoff.yaml                 # PM → agent record
│   ├── plan.md
│   ├── task-checklist.md
│   ├── verification-checklist.md
│   ├── recommended-testing-plan.md
│   ├── post-completion-comments.md
│   ├── review.json                  # `tw session review` output
│   ├── insights.yaml                # proposed node updates
│   └── artifacts/
├── graph/index.yaml                 # derived cache
├── templates/
└── .claude/
    ├── commands/pm-*.md             # 23 slash commands
    └── skills/project-manager/      # 20 refs + 14 examples
```

---

<details>
<summary><b>Demo</b> — CLI samples</summary>

```text
$ tw validate --strict --format=json
{
  "version": 1,
  "exit_code": 0,
  "errors": [],
  "warnings": [],
  "fixed": [],
  "cache_rebuilt": true,
  "duration_ms": 47
}

$ tw status --format=rich
my-project (MP)
  Issues: 23  (backlog=8, todo=6, in_progress=4, in_review=3, verified=1, done=1)
  Concept nodes: 17 active, 2 stale
  Sessions: 4  (1 executing, 1 in_review, 2 completed)
  Critical path: MP-1 → MP-7 → MP-12 → MP-18  (length 4)

$ tw session monitor
session-auth-rework  executing  source=stream-json
  turn: 12
  cost: $0.84
  latest tool: Edit
  branch: feat/session-auth-rework (PR #42)

$ tw uuid --count 3
a1b2c3d4-e5f6-4789-abcd-ef0123456789
f9e8d7c6-b5a4-4321-8765-432109876543
12345678-90ab-4cde-8f01-234567890abc
```

</details>

<details>
<summary><b>Why drift matters</b></summary>

Agents can't build against a tracker that lies to them.

- **Issue text drifts from code.** The endpoint moves; the issue doesn't. Next agent builds against stale info.
- **Context is scattered.** Linear, Notion, Google Docs, Terraform. Agents burn tokens reconciling.
- **Parallel agents stomp.** Without atomic key allocation, they collide on branches and IDs.
- **Reconciliation is a tax.** Mechanical search-and-replace across docs is exactly what LLMs are bad at.

Tripwire puts everything in one repo, content-hashes the graph, and validates before the next agent reads it.

</details>

<details>
<summary><b>Under the hood</b> — dual IDs, graph cache, freshness</summary>

**Dual IDs.** Every entity has a `uuid4` and a human key like `MP-42`, allocated under `fcntl.flock`. Branch-merge collisions resolve via UUID.

**Concept graph with content hashing.** A node pins to a file region:

```yaml
source:
  repo: myorg/backend
  path: src/api/routes/auth.py
  lines: [45, 82]
  content_hash: "sha256:e2c5a..."
```

`tw node check` rehashes and compares. Outcomes: `FRESH` / `STALE` / `SOURCE_MISSING`.

**Graph cache.** `graph/index.yaml` is an incremental edge cache, rebuilt under `fcntl.flock`. `validate` calls `ensure_fresh`.

**Auto-fix subset.** `tw validate --fix` repairs timestamps, drifted counters, missing UUIDs, and bidirectional mismatches. Everything else is on the agent.

**Canonical spawn config.** `claude -p` args come from deep-merged YAML (session > project > default). Override the keys you care about; inherit the rest.

**The PM skill.** 20 reference docs and 14 canonical examples. The agent reads the example; the validator catches bad examples.

</details>

<details>
<summary><b>Worked example</b> — scoping from planning docs</summary>

1. `tw init my-project` — derives `MP` from the name.
2. `/pm-scope Build a knowledge base. Planning docs in ./plans/.`
3. The PM skill calls `tw brief`, then reads `plans/*.md`.
4. The agent writes 20 issues, 15 nodes, 3 sessions.
5. `tw validate --strict` — fix errors, re-run, clean.
6. Commit. `tw status` shows a connected graph with a critical path.

Everything resolves. One clone carries the whole project.

</details>

<details>
<summary><b>What we learned building this</b></summary>

Running a real PM agent against an 8,000-line planning corpus surfaced seven recurring failure modes.

See [`docs/learnings.md`](docs/learnings.md).

</details>

---

## License

MIT. See `LICENSE`.
