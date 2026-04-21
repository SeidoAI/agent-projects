# Tripwire v0.7 — unified design

**Status**: approved design (revised 2026-04-20 after configurability audit)
**Date**: 2026-04-20
**Supersedes**:
- `2026-04-16-v07-pm-monitor.md`
- `2026-04-17-v07-issue-developer-notes.md`

**Summary**: Major release. Renames `keel` → `tripwire` (v0.7a), then
ships a configurability pass, full PM session lifecycle (monitor, review,
complete), per-issue artifact enforcement, canonical spawn configuration,
CI infrastructure, and vocabulary alignment — all v0.7b.

---

## 1. Context

After v0.6c we can spawn local sessions in worktrees, compute dependency
agendas, and track session lifecycle. Gaps remaining:

- PM goes idle after spawn; no structured way to monitor agents.
- No tool reviewing PR diffs against issue specs.
- No end-of-lifecycle command (close issues, reconcile nodes, cleanup).
- Spawn invocation hardcodes flags + prompt in Python.
- Every PR review flags missing `developer.md` / `verified.md`; nothing
  enforces them.
- Session phase vocabulary and issue status vocabulary mean the same
  things using different words.
- No CI for tripwire itself or for projects it manages.
- `keel` name is overloaded in the Python ecosystem.
- A drift audit surfaced multiple items that should be YAML-configurable
  per the original vision but got hardcoded: `ArtifactPhase`, `AgentType`,
  branch type prefixes, spawn invocation, slash command bodies.

v0.7 closes all of this and re-asserts the configurability principle.

---

## 2. Design principles

These principles are the stance tripwire takes. They're what a user
adopts when they adopt the tool. Every v0.7 feature is grounded in
one or more of them, and every v0.8+ design decision measures against
them. The five key principles go in the README verbatim; supporting
principles live in CONTRIBUTING / ARCHITECTURE docs.

### 2.1 The graph is the synchronization layer that makes drift impossible

**Problem**: AI-driven development across multiple systems (issue
trackers, docs, code comments, PR descriptions, ADRs) produces
redundant descriptions of the same concept. Every copy drifts. Agents
burn tokens reconciling, or pick one source and produce work against
stale understanding. This is the tax that kills multi-system
AI-assisted workflows.

**Stance**: Tripwire's concept graph is not a documentation tool.
It's the *single source of truth* for every domain concept the project
models. Everything else — issues, PR descriptions, code comments,
READMEs, workspace nodes across repos — references nodes by pointer
(`[[node-id]]`). There is one place to update; there is no alternative
location for the same information to live.

Structurally, drift is impossible because there is nothing to sync:
only one copy of each concept exists. Workspaces extend the same
principle across repos — shared concepts live once in a workspace,
referenced by many projects.

Adopting tripwire means committing to maintain a single canonical
answer to "what does this system include and what does it mean?"
The graph is ontological infrastructure; nodes are how the system
knows itself.

### 2.2 Deviation is expected; tripwires catch what prevention can't

**Problem**: Agents drift during execution. Prevention requires
crippling autonomy; tolerance produces wrong PRs. You can't stop
drift, and you can't live with it.

**Stance**: Design for the failure, not against it. Validators emit
warnings into the agent's most recent context. Recent context carries
more weight in LLM attention, so warnings placed there have a higher
probability of being addressed before the agent proceeds. Flow
resumes with the deviation surfaced, not halted.

Tripwires are sensors, not locks — lightweight enough to not kill
autonomy, explicit enough to redirect cleanly. This is the mechanism
the tool is named for.

### 2.3 Config over convention, with opinions

**Problem**: Tools that hardcode workflows become obstacles for any
team that doesn't match them. Tools with no opinions push every
decision back onto the team and waste their attention on plumbing.

**Stance**: Tripwire ships opinionated defaults in YAML — our best
current guess at how sessions should spawn, what artifacts are
required, what statuses mean, what the agent spawn prompt should say.
Projects override where they legitimately differ.

Tripwire is opinionated about **what matters for the mechanism**:
validation as a gate, artifacts as evidence, single-agent sessions,
the graph as canon. These are not configurable because softening them
breaks the model.

Tripwire is configurable about **what legitimately varies per team**:
status vocabularies, branch conventions, slash command bodies, spawn
invocation details, artifact specs. The override hierarchy is
universal:

1. Session-level YAML (highest)
2. Project-level YAML (`project.yaml`, `<project>/enums/`, `<project>/.tripwire/`)
3. Tripwire-shipped defaults (lowest)

The opinions live in the YAML, not in Python code. Python consumes
the YAML; it doesn't enumerate the values.

### 2.4 Work compounds; sessions are knowledge-producing events

**Problem**: Most AI-agent workflows produce code without producing
understanding. Session 3 can't benefit from Session 1 because Session
1 left behind commits but nothing else. The codebase accretes; the
understanding does not.

**Stance**: The deliverable of a session is the PR *plus* the updated
concept nodes, developer notes, and verified notes. A session that
ships code without updating what the project knows about itself has
made the project worse — the next agent inherits more confusion, not
less.

Status advancement is gated on artifact production because artifacts
are where the knowledge lives. "Done" means "the code is merged *and*
the understanding is updated." Sessions that can't produce meaningful
updates to the graph are probably sessions that should have been
scoped differently.

### 2.5 Decomposition is a first-class product

**Problem**: Execution quality is bounded by framing quality. Bad
decomposition — vague goals, missing acceptance criteria, wrong
dependencies — means agents work hard on misframed problems. This is
the most common cause of poor AI-agent output.

**Stance**: PM work — scoping, plan writing, session layout,
acceptance criteria, dependency DAGs — is the highest-leverage work
in the project. Not overhead. Not planning-before-real-work. The
decomposition *is* a deliverable that deserves quality, review, and
iteration.

This is why tripwire has more PM-facing features than execution-facing
ones, why `/pm-scope` is its own slash command, why agendas have
critical paths, and why `/pm-session-review` is a structured process
rather than rubber-stamping.

---

### Supporting principles

These are load-bearing for specific features but less central to the
overall stance. They live in CONTRIBUTING / ARCHITECTURE rather than
the README.

**Agents forget; the repo remembers.** Every piece of shared
understanding lives in versioned files. Agents rebuild context from
the repo at session start. No sidecar state, no stowed memory, no
hosted service holding truth. The repo is the externalized long-term
memory of the team — humans, PM agents, execution agents, and whatever
comes next.

**Reasoning must be written, not just performed.** Agents do enormous
amounts of reasoning in a session; the code captures outcomes, not
rationale. Every session produces explicit reasoning artifacts
(`plan.md`, `developer.md`, `verified.md`, comments). Reasoning that
isn't written is reasoning that didn't happen.

**Raise the floor, not the ceiling.** Across 100 agent sessions,
variance is enormous. We optimize for the bottom quartile. Tripwires
catch the disasters. Required artifacts catch skipped reasoning.
Validation catches hallucinations. Strong spawn defaults mean even a
weak session starts from a good invocation. The best sessions don't
need tripwire and won't notice it; the worst sessions are the reason
tripwire exists.

**PM throughput is the bottleneck; tool it accordingly.** Agents are
already faster than PMs can review. PMs need tools that operate at
PM speed: monitor (self-paced), review (structured, evidence-based),
complete (orchestrated close-out), agenda (DAG interpretation). The
CLI + slash wrapper pattern (below) is specifically so PM judgment
only enters where judgment is required; mechanical work stays
mechanical.

**Verification is explicit, attributable, and checked.** Every
artifact declares who produced it. Verification produces its own
artifact with evidence mapped to acceptance criteria. "Done" means
"verified with evidence," not "merged."

**One substrate for humans and agents.** Humans and agents read the
same files, make the same commits, follow the same conventions. No
human-only channels (no Slack threads carrying decisions, no external
docs carrying truth). Human interventions are visible in git history
identically to agent work.

**Single-agent sessions.** One agent per session. Agents cannot spawn
sub-agents via the Agent tool or `/batch`. The PM decomposes work into
sessions; sessions don't re-decompose at runtime. Enforced at spawn
time via `--disallowedTools Agent`.

**Slash command wrapper pattern.** Every feature ships in two layers:
a deterministic CLI command (`tripwire <verb>`) that does mechanical
work and exits with a code, and a slash command wrapper (`/pm-<verb>`)
that orchestrates CLI calls, injects LLM judgment at decision points,
and produces PM-level outputs. The CLI is the source of truth; the
slash command layers interpretation.

### Explicit non-principles

- Not "zero Python hardcoding." Schema, validation mechanics, and CLI
  plumbing live in Python.
- Not "every workflow configurable." The shipped workflows are
  opinions. Projects can override slash command bodies if they need
  to diverge.
- Not "backwards compatible." Pre-1.0 means no legitimate legacy data
  to preserve; breaking changes happen as one clean migration PR, not
  as dual-mode parsers. (Engineering discipline; see CONTRIBUTING.)

---

## 3. Scope summary

| § | Feature | Phase |
|---|---|---|
| 4 | Rename `keel` → `tripwire` | v0.7a |
| 5 | Configurability pass (externalize hardcoded items) | v0.7b Phase 0 |
| 6 | Vocabulary alignment + new `verified` status | v0.7b Phase 1 |
| 7 | Per-issue artifacts | v0.7b Phase 2 |
| 8 | Canonical spawn configuration | v0.7b Phase 3 |
| 9 | Session monitor | v0.7b Phase 4 |
| 10 | Session review | v0.7b Phase 5 |
| 11 | Session complete | v0.7b Phase 6 |
| 12 | CI + PyPI + project workflow templates | v0.7b Phase 7-8 |

**Non-goals for v0.7:**
- Real verification agent (PM fills the verified role)
- Agent messaging MCP (monitor uses stream-json only)
- Container-aware monitoring
- Auto-remediation by default
- Multi-project workspace monitor
- Grandfather / legacy vocabulary aliases

---

## 4. v0.7a — Rename to `tripwire`

### 4.1 Rationale

The current name `keel` collides with multiple adjacent Python packages;
AI agents routinely hallucinate keel-named libraries. Renaming before
any PyPI publish is cheap (downstream = only 3 test projects).

The new name encodes the core mechanism (§2.2).

### 4.2 Changes

| Layer | Before | After |
|---|---|---|
| Package name | `keel` | `tripwire` |
| CLI commands | `keel <subcommand>` | `tripwire <subcommand>` + `tw` alias |
| Import path | `keel.core.*` | `tripwire.core.*` |
| Repo name | `SeidoAI/keel` | `SeidoAI/tripwire` |
| Config field | `project.yaml.keel_version` | `tripwire_version` |
| Lock file | `.keel.lock` | `.tripwire.lock` |
| Hidden dir | `.keel/merge-briefs/` | `.tripwire/merge-briefs/` |
| Project override dir | n/a (didn't exist) | `.tripwire/commands/`, `.tripwire/spawn/` |
| Log dir | `~/.keel/logs/` | `~/.tripwire/logs/` |
| Workspace field | `keel_version` | `tripwire_version` |
| Brand in docs | "keel" | "tripwire" |

### 4.3 CLI entry points

```toml
[project.scripts]
tripwire = "tripwire.cli.main:cli"
tw = "tripwire.cli.main:cli"
```

`tripwire` canonical in docs; `tw` is the ergonomic alias matching the
`gh` / `uv` / `rg` pattern.

### 4.4 PyPI name

Check `tripwire` availability at the start of Phase 8. Fallback:
`tripwire-pm`. The Python package name stays `tripwire` regardless.

---

## 5. Phase 0 — Configurability pass

### 5.1 The problem

Drift audit (2026-04-20) found these items hardcoded in ways that
violate §2.3:

| Item | Current location | New YAML home |
|---|---|---|
| `ArtifactPhase` | Python `Literal` in `models/manifest.py:16` | `src/tripwire/templates/enums/artifact_phase.yaml` + project override |
| `AgentType` | Python `Literal` in `models/manifest.py:15` | `src/tripwire/templates/enums/agent_type.yaml` + project override |
| Branch type prefixes | `ALLOWED_TYPES` tuple in `branch_naming.py:18` | `src/tripwire/templates/enums/branch_type.yaml` + project override |
| Spawn invocation (flags + prompt template) | Python string in `session.py::_launch_claude` | `src/tripwire/templates/spawn/defaults.yaml` (§8) |
| Project-level artifact manifest override | Only session-level overrides exist | `project.yaml.artifact_manifest_overrides` + new `issue_artifact_manifest_overrides` |
| Slash command bodies | Keel-shipped templates only | Projects override at `<project>/.tripwire/commands/<name>.md` |

### 5.2 Pattern: Python schema, YAML values

For each item above, the approach is the same:

1. **Python** declares the *shape* of the concept via a Pydantic model.
   The model's fields are `str`, not `Literal`. Validation happens at
   load time.
2. **Tripwire templates** ship a default YAML populated with tripwire's
   opinions.
3. **Project config** can override at `<project>/enums/<name>.yaml`
   (for enum-like values) or via specific fields in `project.yaml`
   (for structured overrides).
4. **Loader** (one per concept) reads project first, falls back to
   tripwire default. Loader returns the typed values; validators
   consume them.

This mirrors the existing pattern already used for `IssueStatus`,
`SessionStatus`, and status transitions — which is why those didn't
drift.

### 5.3 Detailed migration — `ArtifactPhase`

Canonical example; all other migrations follow the same shape.

**Before:**
```python
ArtifactPhase = Literal["planning", "implementing", "verifying", "completion"]
```

**After:**

Python (`models/manifest.py`):
```python
# ArtifactPhase is loaded from enums/artifact_phase.yaml.
# Default: {planning, in_progress, in_review, verified, done}
# (see §6 for the new `verified` phase).
# Models use str; loader validates against enum at runtime.
class ArtifactEntry(BaseModel):
    produced_at: str
    # ... validated against loaded ArtifactPhase at manifest load
```

YAML (`src/tripwire/templates/enums/artifact_phase.yaml`):
```yaml
name: ArtifactPhase
description: Stages at which artifacts are produced
values:
  - id: planning
    label: Planning
    description: PM scoping and plan writing
  - id: in_progress
    label: In progress
    description: Execution agent implementing
  - id: in_review
    label: In review
    description: PM reviewing PR
  - id: verified
    label: Verified
    description: QA agent verifying tests + acceptance criteria
  - id: done
    label: Done
    description: Complete and merged
```

Loader: reuses existing `core/enum_loader.py` machinery. No new code.

**Project override:** write `<project>/enums/artifact_phase.yaml` with
a different value set. Validator catches manifest entries referencing
unknown phases.

### 5.4 Detailed migration — spawn invocation

See §8 (spawn configuration) — the full migration covers prompt
template, flags, system prompt append, and per-session/project
override precedence.

### 5.5 Detailed migration — slash command bodies

**Before:** `src/tripwire/templates/commands/pm-*.md` ships tripwire's
version only. Projects cannot override.

**After:** Loader looks in this order:
1. `<project>/.tripwire/commands/<name>.md`
2. `src/tripwire/templates/commands/<name>.md`

A project wanting a different `/pm-scope` workflow copies the shipped
version to `.tripwire/commands/pm-scope.md` and edits.

### 5.6 What's NOT externalized in v0.7

Deferred to v0.8+ (mentioning to set expectations):
- Validator check implementations (each is a Python function; YAML
  DSL for validation is out of scope)
- Core CLI command structure (which subcommands exist)
- Agent / coordination patterns (these are CLAUDE.md guidance for
  the agent ecosystem, not tripwire config)

---

## 6. Phase 1 — Vocabulary alignment + verified stage

### 6.1 New issue status order

```
backlog → todo → in_progress → in_review → verified → done
```

| Status | Meaning | Who drives | Artifact required at entry |
|---|---|---|---|
| `backlog` | Captured but not triaged | - | - |
| `todo` | Triaged, ready for pickup | PM | - |
| `in_progress` | Execution agent working | Execution agent | - |
| `in_review` | PR opened, PM reviewing code/project PR | PM agent | `developer.md` |
| `verified` | PR merged, QA agent ran acceptance tests | QA agent (v0.8+; PM fills in v0.7) | `verified.md` |
| `done` | Closed — concept nodes reconciled, followups logged | PM | - |

**Why split `in_review` and `verified`:** code review (PM) and acceptance
testing (QA) are distinct activities. A PR can pass PM review but fail
acceptance testing. Until a real QA agent ships, the PM fills the
verified role and writes `verified.md`. The status distinction stays
because it'll matter when the QA agent lands.

### 6.2 Phase vocabulary alignment

`ArtifactPhase` values (loaded from YAML per §5.3) map 1:1 with
`IssueStatus`, except for `planning` (session-only):

| ArtifactPhase | IssueStatus analog |
|---|---|
| `planning` | (session-only, no analog) |
| `in_progress` | `in_progress` |
| `in_review` | `in_review` |
| `verified` | `verified` |
| `done` | `done` |

Old phase names (`implementing`, `verifying`, `completion`) are gone —
no grandfather or alias layer (see "Explicit non-principles" in §2).

### 6.3 Layer-2 coherence test

A unit test asserts `set(ArtifactPhase enum) - {"planning"}` is a
subset of `set(IssueStatus enum)`. Both values are loaded from the
tripwire-shipped default YAML (not project overrides — the shipped
defaults must stay aligned; projects can diverge if they want).

Test fails if anyone adds a phase that doesn't match an issue status
without explicitly adding it to `SESSION_ONLY_PHASES = {"planning"}`.

### 6.4 Layer-3 coherence validator

Validator check runs on every `tripwire validate`. Session↔issue
alignment:

| Session status | Allowed issue statuses | Violation |
|---|---|---|
| `planning` | `backlog`, `todo` | warn on later |
| `in_progress` | `todo`, `in_progress`, `in_review` | warn on later |
| `in_review` | `in_review`, `verified`, `done` | error on earlier |
| `verified` | `verified`, `done` | error on earlier |
| `done` | `done` | error on anything else |

Codes:
- `coherence/issue_status_lags_session` (warning)
- `coherence/issue_status_ahead_of_session` (error)

### 6.5 Migration

All session YAMLs across 3 test projects: status values remap per
§6.2. Old `implementing` → `in_progress`, `verifying` → `in_review`,
`completion` → `done`. No issue currently uses `verified`; new
issues produced after this phase can populate it.

---

## 7. Phase 2 — Per-issue artifacts

### 7.1 Manifest

Shipped at `src/tripwire/templates/issue_artifacts/manifest.yaml`:

```yaml
artifacts:
  - name: developer
    file: developer.md
    template: developer.md.j2
    produced_by: execution-agent
    owned_by: execution-agent
    required: true
    required_at_status: in_review   # written before PM review

  - name: verified
    file: verified.md
    template: verified.md.j2
    produced_by: verification-agent
    owned_by: verification-agent
    required: true
    required_at_status: verified    # written by QA agent (PM in v0.7)
```

Project overrides at `project.yaml.issue_artifact_manifest_overrides`
(list of entries appended/replacing shipped entries by `name`).

### 7.2 Schema

```python
class IssueArtifactEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    file: str
    template: str
    produced_by: str  # validated against agent_type.yaml at load time
    owned_by: str | None = None
    required: bool = True
    required_at_status: str  # validated against issue_status.yaml at load time
```

All stringly-typed; loaders validate against the project's active enums.

### 7.3 Validator: `check_issue_artifact_presence`

For each issue, for each required entry: if `issue.status ≥
required_at_status`, the file must exist. Emits
`issue_artifact/missing` (error).

Status ordering derived from `project.yaml.status_transitions` + the
loaded `IssueStatus` enum (no hardcoded order).

### 7.4 Status transition guards

- `in_progress → in_review`: blocked without `developer.md`
- `in_review → verified`: blocked without `verified.md`
- `verified → done`: no artifact gate (done means cleanup complete)

### 7.5 CLI

```
tripwire issue artifact init <issue-key> <artifact-name> [--force] [--produced-by AGENT]
tripwire issue artifact list <issue-key> [--format text|json]
tripwire issue artifact verify <issue-key>
```

### 7.6 Slash command wrapper

`/pm-issue-artifact` (new): wraps the CLI with PM judgment on what
content to populate in the artifact. For `verified.md` this runs a
structured review against acceptance criteria; for `developer.md`
this would be the agent at completion time.

### 7.7 Migration — backfill

Every issue at `in_review` or later gets `developer.md` backfilled
with a placeholder stub. Every issue at `verified` or `done` gets
`verified.md` backfilled with a stub (attribution: `pm-agent`,
verdict: `approved`).

Stub template includes a "This artifact was created retroactively
during v0.7 migration. See PR <number>." paragraph.

### 7.8 Agent insights capture

**Problem**: The executing agent holds privileged knowledge about
what it just did — decisions, paths not taken, lessons — that no one
else has direct access to. Most of it is implicit in the code. A
small but valuable subset is durable insight that future agents in
the same area would benefit from inheriting. This is currently lost
when the session ends.

**Mechanism**: At session end, the executing agent optionally
produces `sessions/<session-id>/insights.yaml` proposing concept-node
additions or updates based on what it learned.

**Schema**:

```yaml
# Only written if the agent has genuine insights worth elevating.
# Absent or empty file is the expected default — silence is valid.
proposals:
  - kind: new_node
    id: pg-vacuum-tuning
    type: decision
    name: PostgreSQL VACUUM tuning for high-write workloads
    body: |
      During <session-id> we found the default autovacuum settings
      don't keep up with our write volume. Changed
      autovacuum_vacuum_scale_factor 0.2 → 0.02, autovacuum_naptime
      60s → 10s. Documenting so future perf work on PG tables inherits.
    related: [database, postgres-config]
    rationale: >
      Operational tuning that would otherwise live in tribal knowledge.

  - kind: update_node
    id: auth-system
    delta: |
      Session added refresh-token rotation on suspicious IP change.
      Current node description doesn't mention rotation policy at all.
    rationale: >
      Node description is stale w.r.t. security property now enforced.
```

Fields:
- `kind`: `new_node` or `update_node`
- `id`: existing node id (update) or proposed new id (new_node)
- `type`: node type (new_node only; required). Validated against the active
  `node_type` enum at load time.
- `name`: human-readable title (new_node only; required)
- `body` or `delta`: full body (new_node) or described change (update_node)
- `related`: other node ids this connects to (new_node only)
- `rationale`: why this deserves to be durable

**Agent prompt instruction** (added to spawn system prompt):

> Before you end the session: ask honestly — did you learn anything
> future agents in this area would benefit from inheriting? Not "what
> did I do" (that's `developer.md`) but "what insight would I want
> the next agent working near this to start from?" If yes, propose it
> in `insights.yaml` as a node addition or update. If nothing
> qualifies — if every insight is either obvious, already in a node,
> or specific to this session — leave the file absent. **Do not
> force it.** Overeager proposals add noise to the graph. Silence is
> a valid answer.

**PM review at complete time**: `/pm-session-complete` surfaces
proposed insights alongside the existing node-reconciliation diffs.
For each proposal, the PM agent decides:
- **Accept**: add or update node as proposed (may edit wording
  before committing).
- **Reject**: insight is noise, ephemeral, or already captured
  elsewhere.
- **Defer**: interesting but needs more context; the PM logs a new
  curation issue and dismisses for now.

Accept/reject rates per agent get tracked in engagement records —
useful signal for tuning agent prompts over time.

**CLI**:

```
tripwire session insights list <session-id> [--format text|json]
tripwire session insights apply <session-id> --proposal <id>
tripwire session insights reject <session-id> --proposal <id> [--reason TEXT]
```

`apply` writes the node (new) or node update (existing), with
commit attribution tying back to the session. `reject` records the
dismissal in `sessions/<session-id>/insights.rejected.yaml` for
audit.

**Risks and mitigations**:
- Overproduction → explicit "do not force it" in prompt; PM rejection
  discipline; accept/reject ratio tracked.
- Duplicate proposals → validator warns if proposed node id collides
  with existing; PM can reject or redirect as an update.
- Gestural insights ("X is important" without content) → PM rejects
  with a templated reason ("insufficient specificity").
- Mutually contradictory proposals across parallel sessions → caught
  at PM merge time; PM reconciles before applying.

This is the concrete mechanism for principle §2.4 (work compounds)
— the durable knowledge artifact that ensures sessions leave the
project knowing more about itself than before.

---

## 8. Phase 3 — Canonical spawn configuration

### 8.1 Canonical YAML

Ships at `src/tripwire/templates/spawn/defaults.yaml`:

```yaml
# Default spawn configuration. Projects override via
# project.yaml.spawn_defaults. Sessions override via
# session.yaml.spawn_config. Precedence: session > project > tripwire default.

invocation:
  command: claude
  args:
    - "-p"
    - "{{ prompt }}"
    - "--name"
    - "{{ session_id }}"
    - "--session-id"
    - "{{ claude_session_id }}"
    - "--effort"
    - "{{ effort }}"
    - "--model"
    - "{{ model }}"
    - "--fallback-model"
    - "{{ fallback_model }}"
    - "--permission-mode"
    - "{{ permission_mode }}"
    - "--disallowedTools"
    - "{{ disallowed_tools | join(',') }}"
    - "--max-turns"
    - "{{ max_turns }}"
    - "--max-budget-usd"
    - "{{ max_budget_usd }}"
    - "--output-format"
    - "{{ output_format }}"
    - "--append-system-prompt"
    - "{{ system_prompt_append }}"
  background: true                        # nohup & redirect
  log_path_template: "~/.tripwire/logs/{{ project_slug }}/{{ session_id }}-{{ timestamp }}.log"

config:
  model: opus
  fallback_model: sonnet
  effort: max
  permission_mode: bypassPermissions
  disallowed_tools: [Agent]
  max_turns: 200
  max_budget_usd: 50
  output_format: stream-json

# Jinja template. Rendered at spawn time with `plan`, `session_id`,
# `claude_session_id` (UUID for --resume), `session_name`, `agent`,
# `project_slug`, `branch_type` in scope. Projects can override this
# to change the instructions given to spawned agents.
prompt_template: |
  {{ plan }}

  You are the {{ agent }} agent for session {{ session_id }}.
  Execute the plan. Stop at stop-and-ask points.
  Open a PR titled '{{ branch_type }}({{ session_slug }}): {{ session_name }}' when done.

system_prompt_append: |
  tripwire session: {{ session_id }}; project: {{ project_slug }}
  If context is getting heavy, use /compact to free space.
  Do not use the Agent tool — you are a single-agent session.
  Do not use /batch — the work is already decomposed in your plan.
```

### 8.2 Precedence

1. `session.yaml.spawn_config` (highest)
2. `project.yaml.spawn_defaults`
3. `<project>/.tripwire/spawn/defaults.yaml` (project-wide override)
4. `src/tripwire/templates/spawn/defaults.yaml` (tripwire default)

Merge is deep: each level can override specific keys (e.g., just
`model`) without re-specifying everything.

### 8.3 Python side

`tripwire.core.spawn_config.load(project_dir, session) -> ResolvedSpawnConfig`
returns a fully-merged, rendered configuration. `session.py` consumes
it:

```python
resolved = load_spawn_config(project_dir, session)
args = resolved.render_args(plan=plan, session_id=session.id, ...)
subprocess.Popen(args, ...)
```

No Python code assembles the invocation by string concatenation. No
hardcoded flags.

### 8.4 Per-session override

`session.yaml.spawn_config` is optional but canonical in shape:

```yaml
spawn_config:
  config:
    model: sonnet          # lightweight session
    max_budget_usd: 10
  # prompt_template and system_prompt_append inherited from project/default
```

### 8.5 Resume by name

Uses `--resume <session-id>` (matching `--name` from spawn). Survives
reboots; independent of PID. `--fork-session` used on re-engagement
after failed attempts to preserve conversation history with a new
engagement ID.

### 8.6 Slash command wrapper

`/pm-session-spawn` (already exists from v0.6c) now consumes the
canonical config. No user-visible change for common paths; advanced
users can customize prompt/flags per project without modifying
tripwire source.

---

## 9. Phase 4 — Session monitor

Unchanged from the prior revision. Brief recap:

- CLI: `tripwire session monitor` (one-shot snapshot)
- Slash: `/pm-session-monitor` (self-paced loop via `/loop` dynamic)
- Primary data source: stream-json log (enabled by §8 config)
- Fallback: git + gh polling
- Auto-actions: read-only by default; slash-command natural-language args
  elevate to targeted auto-remediation
- Commits status snapshots to project repo per tick

Events monitored: commits, PR open, CI status, process alive, stuck
detection, cost threshold, session complete.

---

## 10. Phase 5 — Session review

### 10.1 Interface

- CLI: `tripwire session review <session-id> [--pr <number>]`
- Slash: `/pm-session-review <session-id>`

Local PM execution only (no GitHub Action counterpart in v0.7).

### 10.2 Checks

- Per-issue acceptance criteria verification (read issue.yaml, map to
  PR diff, flag unverified)
- Deviation detection (unspec'd files, dependencies, layout)
- Plan adherence (each plan.md step has evidence)
- Stop-and-ask audit (triggered conditions the agent didn't halt on)

### 10.3 Output channels

1. PM session output (text or JSON)
2. PR comments — primary PM↔PR channel. Summary comment + inline
   file:line comments for findings.
3. `verified.md` side-effect per §10.4

### 10.4 verified.md side-effect

For each issue in the session:

- If `issues/<key>/verified.md` doesn't exist: write from review output,
  attribution `pm-agent`.
- If exists with non-PM attribution (future QA agent): read-only; factor
  existing content into review output.
- If exists with `pm-agent` attribution: append `## Re-review <date>`
  section (preserve history).

### 10.5 Exit codes (blocking)

- 0: approved
- 1: approved with notes (warnings only)
- 2: unverified criteria or plan divergence (blocks subsequent
  `/pm-session-complete` unless `--force-review`)

---

## 11. Phase 6 — Session complete

### 11.1 Interface

- CLI: `tripwire session complete <session-id> [flags]`
- Slash: `/pm-session-complete <session-id> [closing-note]`

### 11.2 CLI behavior (mechanical)

1. Verify status is `in_review` or `verified` (refuse otherwise;
   `--force` overrides).
2. Verify PR merged (refuse with `complete/pr_not_merged` unless
   `--force`).
3. Verify per-issue artifacts present (§7.3 enforcement; no override).
4. Verify most recent session review exit code ≤ 1 (refuse unless
   `--force-review`).
5. Compute concept-node reconciliation diffs (advisory — CLI does not
   apply).
6. Transition session.status → `done`.
7. Update engagements with `ended_at` / `outcome`.
8. Worktree cleanup (unless `--skip-worktree-cleanup`).
9. Report: issues to close, sessions unblocked, worktrees removed,
   node diffs to review.

### 11.3 Slash command behavior (PM judgment)

1. Run `tripwire session complete <id> --dry-run` to preview.
2. Run `/pm-session-review` if not already run at current HEAD.
3. For each node with a diff from step 5 above, PM agent reads the
   proposed change, decides whether to apply (may edit wording), commits.
4. `tripwire refs reverse <node-id>` logs downstream sessions affected.
5. Close each issue → `done` with completion comment.
6. Transition issues: agents move to `verified` (via `tripwire issue
   status set <key> verified` → emits acceptance test run), then `done`.
7. `tripwire validate --strict` (Layer 3 coherence catches slippage).
8. Remove worktrees.
9. Commit: `complete: <session-id> (ISSUE-KEYS...)`.
10. Report summary.

---

## 12. Phase 7-8 — CI + PyPI + project templates

### 12.1 Tripwire-tool CI (Phase 7)

`.github/workflows/ci.yml` in tripwire repo. On every PR and push to
main:
- uv sync
- ruff check
- ruff format --check
- pytest -q

Python 3.13, ubuntu-latest. Target: <3 min.

### 12.2 PyPI publish (Phase 8)

`.github/workflows/publish.yml`. On tag push matching `v*`:
- uv build
- uv publish (token from `PYPI_API_TOKEN` secret)

Release = PR bumping `pyproject.toml version` + tag push. First
release: `v0.7.0` under `tripwire` (or `tripwire-pm` fallback).

### 12.3 Project CI template

Shipped at `src/tripwire/templates/project/.github/workflows/tripwire.yml.j2`.
Rendered by `tripwire init` into `<project>/.github/workflows/tripwire.yml`:

```yaml
name: Tripwire checks
on: [pull_request, push]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv tool install tripwire=={{ tripwire_version }}
      - run: tripwire validate --strict --format=json
      - run: tripwire lint scoping
      - run: tripwire lint handoff
      - run: tripwire lint session
      - run: tripwire brief --format=json > /dev/null
```

Pinned version reads from `project.yaml.tripwire_version`.

### 12.4 `tripwire ci install`

For existing projects. Renders the template, refuses if file exists
unless `--force`.

### 12.5 `tripwire init` defaults to CI

Adds `.github/workflows/tripwire.yml` by default. `--skip-ci` opts out.

### 12.6 Version bump workflow

1. Edit `project.yaml.tripwire_version` → new version
2. `tripwire ci install --force`
3. Commit both changes in one PR
4. CI on that PR runs the new tripwire version

---

## 13. Cross-feature integration

### 13.1 Monitor → Review

Monitor detects PR open → auto-runs `/pm-session-review` (read-only
default). Findings post to PR comments. Exit 2 surfaces as blocking
in monitor output.

### 13.2 Review → verified.md

Review writes `verified.md` via the side-effect path (§10.4). Single
path for producing the artifact in v0.7.

### 13.3 Complete → Review + Artifacts + Node recon

Complete orchestrates review (if needed), per-issue artifact
enforcement, PM-reviewed node reconciliation, issue close loop, and
coherence validation (§6.4).

### 13.4 Spawn → Monitor

stream-json output (§8 config) is the monitor's primary data source.
--name enables resume-by-name.

### 13.5 CI → Per-issue artifacts + Coherence

Project CI runs `tripwire validate --strict`, which enforces §7.3 and
§6.4. Merge gate.

### 13.6 Configurability (§5) → everything

Every phase after Phase 0 consumes YAML-loaded configuration, never
Python literals. A project customizing its workflow edits YAML.

---

## 14. Release sequencing

### 14.1 v0.7a — Rename

Single branch, single merge. ~1-2 hours agent work.

### 14.2 v0.7b — Features

Single branch (`feature/v0.7b`), 8 phases, each mergeable independently:

| Phase | Feature | Depends on |
|---|---|---|
| 0 | Configurability pass | v0.7a |
| 1 | Vocabulary + verified | Phase 0 (so enums are YAML) |
| 2 | Per-issue artifacts | Phase 1 |
| 3 | Canonical spawn config | Phase 0 |
| 4 | Session monitor | Phase 3 |
| 5 | Session review | Phase 2 |
| 6 | Session complete | Phase 5 |
| 7 | Tripwire-tool CI | independent |
| 8 | PyPI + project CI | Phase 7 |

---

## 15. README updates

Phase 0 includes updating the tripwire README to establish §2 as
foundational. Specifically:

- Add "Design principles" section pulling in §2.1–§2.5 verbatim
  (the five key principles).
- Supporting principles stay in this spec and migrate to
  CONTRIBUTING.md / ARCHITECTURE.md rather than the README.
- Add "How tripwire is configured" subsection pointing to the enum
  override mechanism, spawn config, slash command overrides.
- Update examples to reflect the `tripwire` / `tw` CLI.

---

## 16. Error code summary

| Code | Feature | Severity |
|---|---|---|
| `coherence/issue_status_lags_session` | §6.4 | warning |
| `coherence/issue_status_ahead_of_session` | §6.4 | error |
| `issue_artifact/missing` | §7.3 | error |
| `issue_artifact/wrong_status` | §7.4 | error |
| `complete/not_active` | §11 | error |
| `complete/missing_artifacts` | §11 | error |
| `complete/issue_not_closeable` | §11 | error |
| `complete/worktree_dirty` | §11 | error |
| `complete/pr_not_merged` | §11 | error |
| `complete/review_blocking` | §11 | error |
| `monitor/log_missing` | §9 | warning |
| `monitor/session_not_executing` | §9 | error |
| `review/unverified_criteria` | §10 | error (exit 2) |
| `review/plan_deviation` | §10 | error (exit 2) |
| `review/unspec_files` | §10 | warning |
| `ci/workflow_exists` | §12 | error (without --force) |
| `spawn/config_invalid` | §8 | error |
| `enum/unknown_value` | §5 | error (generic) |

---

## 17. Testing

Consolidated test counts, detail in draft specs:

| Feature | New tests |
|---|---|
| Configurability pass | ~12 (enum loader per concept, precedence, schema validation) |
| Vocabulary + verified | ~10 |
| Per-issue artifacts | ~15 |
| Spawn config | ~10 (precedence, rendering, flag assembly) |
| Monitor | ~12 |
| Review | ~10 |
| Complete | ~10 |
| CI + PyPI | ~6 |
| Rename (v0.7a) | smoke tests pass |

---

## 18. Open items for implementation

- PyPI `tripwire` availability check at start of Phase 8.
- `--exclude-dynamic-system-prompt-sections` audit against current
  Claude Code CLI version before inclusion in spawn defaults.
- Specific keys of `project.yaml.spawn_defaults` and
  `project.yaml.issue_artifact_manifest_overrides` — fine detail for
  Phase 0 and 2 implementation.
- Stream-json event classification (which types to hard-parse vs treat
  as info) — fine detail for Phase 4.

---

## 19. Cross-references

- `2026-04-16-v07-pm-monitor.md` — superseded by this document
- `2026-04-17-v07-issue-developer-notes.md` — superseded
- `2026-04-16-session-spawn-agenda-worktrees-design.md` — v0.6c;
  §8 amends the spawn invocation
- Claude Code CLI reference (v2.1.110+)
