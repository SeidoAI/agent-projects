# Keel v0.6 — Workspace + PM Workflow Improvements

**Status**: design approved, ready for implementation planning
**Date**: 2026-04-15
**Replaces**: nothing (additive to v0.5)
**Companion doc**: `docs/backlog.md` (deferred features)

---

## 1. Context

### 1.1 The pain

Keel projects are islands. Every project has its own `nodes/` directory of
domain concepts. Two projects working in adjacent domains end up
re-defining the same concepts ("our auth system," "event schema v2") with
different names, slightly different shapes, and no cross-pollination.
Every new project pays a tax of re-deriving shared knowledge from
scratch.

This is the highest-pain instance of a broader problem categorised as
"no memory across sessions or projects" in the v0.5 retrospective. We
considered four forms of the pain (session→session continuity,
cross-project linking, shared concepts, portfolio view) and ranked
**shared concepts** as the primary target — it has the most concrete
duplication cost, the cleanest mental model (concepts are first-class
entities), and the clearest workflow ("create project pulling
concepts down, sync changes back up"). Portfolio view is a secondary
beneficiary; cross-project refs are deferred as more complex.

### 1.2 The mental model

A workspace is a **centralised synchronisation layer** for shared
nodes. The relationship between a project and its workspace is
git-shaped: project = branch, workspace = main. Projects pull
canonical concepts down, diverge locally as needed, and push back up
explicitly. Sync is never automatic; conflicts surface for agent
mediation rather than silent resolution.

This document specifies the workspace primitive (sections 2-3) and a
bundle of PM-workflow improvements (section 4) that the v0.5 retro
surfaced as ready-to-ship in the same release. Section 5 rationalises
the entire PM slash-command surface for consistency. Sections 6-8
cover workflows, error cases, and testing.

### 1.3 Scope and non-goals

**In scope (v0.6):**

- Workspace primitive (manifest, registry, shared `nodes/` directory)
- Multi-repo physical layout (workspace as separate git repo)
- Node sync via git-aligned commands (`pull`, `push`, `promote`,
  `fork`, `copy`, `merge-resolve`)
- Agent-mediated 3-way merge for non-trivial conflicts
- Bidirectional project↔workspace registry
- Bundled PM improvements: manifest ownership fields, /pm-handoff
  split, structured handoff artifact, `keel lint`, missing CLI
  commands, branch naming convention
- PM slash command surface rationalisation (consistent naming rule)
- Migration of three test projects (`kb-pivot`, `graph-ui-v2`,
  `project-keel-ui-init`) into a `seido-workspace`

**Explicitly out of scope (deferred to backlog):**

- Cross-project refs (`@project/KEY`-style) — useful but complex,
  needs a live resolver, separate spec
- Auto-drift detection with continuous reconcile
- Hybrid YAML+markdown artifact format (separate backlog entry)
- Machine-readable workflow DSL for PM skill workflows
- Workflow-change migration tooling as first-class feature (we ship
  migrations alongside each change, no dedicated tool)
- `keel issue timeline` command
- Remote workspace URLs (local paths only for v0.6)
- Workspace manager as a separate skill (PM skill gains workspace
  commands directly)
- `pm-plan` slash command (deleted; users run `keel plan` directly)

**Handled by parallel UI agent, not in this spec:**

- README updates
- Workspace UI integration

---

## 2. Architecture

### 2.1 Physical layout

```
~/Code/seido/                       # existing parent dir, unchanged
├── seido-workspace/                # NEW: separate git repo
│   ├── .git/
│   ├── workspace.yaml              # manifest: name, member projects
│   ├── nodes/                      # canonical shared concepts
│   │   ├── auth-system.yaml
│   │   └── event-schema-v2.yaml
│   └── .keel.lock
│
├── project-kb-pivot/               # existing repo, unchanged layout
│   ├── .git/
│   ├── project.yaml                # gains: workspace: ../seido-workspace
│   ├── nodes/
│   │   ├── auth-system.yaml        # origin: workspace, scope: workspace
│   │   ├── kb-ingestion-graph.yaml # origin: local, scope: local
│   │   └── webhook-handler.yaml    # origin: local, scope: workspace
│   ├── issues/
│   └── sessions/
│
├── project-graph-ui-v2/            # existing repo, unchanged
└── project-keel-ui-init/           # existing repo, unchanged
```

### 2.2 Architectural properties

- **Workspace is its own git repo** with its own history. Canonical
  node state is what's on workspace's main branch.
- **Projects are physically untouched.** Not moved, not nested, not
  reorganized. Only `project.yaml` gains a single optional field.
- **No filesystem convention required.** Workspace and projects live
  anywhere on disk. Discovery via the `workspace:` pointer in
  `project.yaml` (relative path, absolute path, future remote URL).
- **Project `nodes/` mixes origins.** Frontmatter distinguishes
  workspace-origin from local nodes. Filesystem layout stays flat.
- **Workspace is minimal.** `workspace.yaml`, `nodes/`, lock file.
  No issues, no sessions, no plans. Single-purpose surface.
- **Projects remain valid standalone.** A project without a
  `workspace:` pointer is a regular keel project. Every existing
  project continues to work untouched after upgrade.

### 2.3 Why multi-repo, not monorepo

Considered three layouts: (α) multi-repo, (β) one repo with
projects-as-branches, (γ) one repo with projects-as-directories. Only
β gives true git-branch semantics, but at the cost of long-lived
branches, worktree complexity, and one-project-at-a-time context
switching. γ has all the operational drawbacks of monorepo (branches
span everything, per-project publishing hard) without compensating
benefit. α preserves per-project autonomy (publishing, archival,
handoff stay trivial) and lets us layer git-aligned sync semantics on
top via custom commands. Decision: α.

### 2.4 Git semantics without literal git branches

Sync commands borrow vocabulary and semantics from git (`pull`,
`push`, 3-way merge, common ancestor) without requiring projects to
literally be git branches. The PM agent's mental model is: "project
is conceptually a branch of workspace; sync commands behave like git
remote operations." This gives us merge intuition transfer while
keeping each project as an independent git repo.

---

## 3. Entity schemas

### 3.1 `workspace.yaml` (new)

```yaml
---
uuid: 8b7c6d5e-4f3a-2b1c-9d8e-7f6a5b4c3d2e
name: Seido
slug: seido
description: Shared concepts across Seido projects.
schema_version: 1
keel_version: 0.6.0
created_at: 2026-04-15T14:30:00Z
updated_at: 2026-04-15T14:30:00Z

projects:
  - slug: kbp
    name: kb-pivot
    path: ../project-kb-pivot          # relative to workspace root
    last_pulled_sha: a3f2b1c
    last_pulled_at: 2026-04-15T14:30:00Z
    last_pushed_sha: a3f2b1c
    last_pushed_at: 2026-04-14T09:12:00Z
  - slug: gui
    name: graph-ui-v2
    path: ../project-graph-ui-v2
    last_pulled_sha: a3f2b1c
    last_pulled_at: 2026-04-15T14:30:00Z
---
```

Registry is auto-maintained by `keel workspace pull/push`. Human-edited
only for initial registration or manual cleanup.

### 3.2 `project.yaml` addition

```yaml
# existing project.yaml unchanged, plus:
workspace:
  path: ../seido-workspace             # relative to project root
  # url: git@github.com:seido/workspace.git   # remote (future)
```

Object form (not scalar) reserves room for future expansion without
breaking changes. Absence of the `workspace:` field means standalone
project.

### 3.3 Node frontmatter additions

```yaml
---
uuid: ...
id: auth-system
kind: system
name: Auth System
# ... existing fields unchanged ...

# NEW — every node:
origin: workspace                     # where this node came from
scope: workspace                      # where the author thinks it belongs

# NEW — only when origin=workspace:
workspace_sha: a3f2b1c                # workspace commit at time of pull
workspace_pulled_at: 2026-04-15T14:30:00Z
---
```

**Four state combinations:**

| origin | scope | workspace_sha | meaning |
|---|---|---|---|
| local | local | (absent) | pure project-local; ignored by sync |
| local | workspace | (absent) | promotion candidate; `push` will offer to promote |
| workspace | workspace | present | synced; `pull` updates it; `push` sends local changes up |
| workspace | local | present (kept for audit) | detached fork; sync skips in both directions |

**Validation rules:**

- `workspace_sha` required when `origin: workspace`, forbidden when
  `origin: local`
- `scope: workspace` on a promotion candidate requires the node's
  `id` be globally unique in workspace (checked at push time)
- Fork allowed at any time; sync ops warn user that node will be
  skipped

**Migration for existing projects:** all existing nodes default to
`origin: local, scope: local`. No data loss, no behaviour change
until you pull/push.

### 3.4 `handoff.yaml` (new — bundled in 4.5)

`sessions/<id>/handoff.yaml`:

```yaml
---
uuid: ...
session_id: session-auth-42-setup
handoff_at: 2026-04-15T14:30:00Z
handed_off_by: pm
branch: feat/auth-42-setup            # validated against branch convention
open_questions:                        # things PM couldn't answer
  - "Should retries be exponential or fixed?"
context_to_preserve:                   # decisions made at handoff
  - "Bucket naming uses {{env}}-{{service}} convention (decided 2026-04-14)"
last_verification_passed_at: null      # iterative handoffs carry this
workspace_context:                     # optional
  workspace_nodes_touched: [auth-system, event-schema-v2]
  workspace_sha_at_handoff: a3f2b1c
  stale_nodes: []
---
```

Required when transitioning session to `queued`. Validator and
`keel lint handoff` both enforce shape and branch format.

### 3.5 `manifest.yaml` field additions (4.1)

```yaml
artifacts:
  - name: plan
    produced_at: planning
    produced_by: pm                   # NEW — enum from enums/agent_types.yaml: pm | execution-agent | verification-agent
    owned_by: pm                      # NEW — who updates after creation; same enum as produced_by
    required: true

  - name: task-checklist
    produced_at: implementing         # NEW — was "planning" (incorrect)
    produced_by: execution-agent
    owned_by: execution-agent
    required: true
```

Validator becomes stage-aware: `task-checklist.md` not required
until session enters `implementing`. PM commands stop creating
artifacts they don't own.

---

## 4. Bundled PM workflow improvements

These ship together with workspace as v0.6. Most are orthogonal to
workspace; three intersect.

### 4.1 Manifest ownership fields — MVP

See section 3.5 above. Root cause fix for the ambiguity that caused
the task-checklist creation bug.

### 4.2 Split `/pm-handoff` — MVP

Two explicit commands replace the dual-mode `/pm-handoff`:

```
/pm-session-create <issue-key> [agent-type]   # creates a session for an issue
/pm-session-launch <session-id>               # transitions session to queued
```

Eliminates the workflow drift where `/pm-handoff` either re-created
session artifacts (duplicating `/pm-scope`) or assumed they existed
(undocumented case). See section 5 for the full command surface
rationale.

### 4.3 `keel lint` — MVP

Heuristic checks separate from `keel validate`. Stage-aware:

```
keel lint scoping            # gap-analysis row count, ref density, orphan concepts
keel lint handoff [<id>]     # readiness, missing artifacts, concept freshness
keel lint session <id>       # branch set, open questions recorded, etc.
```

Workspace-aware rules included from day one:

- `lint scoping`: flags workspace-origin nodes behind workspace HEAD
- `lint handoff`: flags unresolved merge briefs
- `lint session`: flags unpushed promotion candidates

Catches "did someone actually do the work" shortcuts the validator
can't.

### 4.4 Missing CLI commands — MVP

- `keel session check <id>` — readiness punch list
- `keel session progress` — aggregate task-checklist status across
  active sessions; workspace-aware at workspace root (portfolio
  rollup)
- `keel refs check` — explicit command (currently only `refs summary`
  exists; verification checklist asks for `refs check`)

Deferred: `keel issue timeline <KEY>` — `git log` works today.

### 4.5 Structured handoff artifact — MVP

`sessions/<id>/handoff.yaml` per section 3.4. Replaces the free-form
markdown handoff comment with structured fields execution agents can
parse reliably.

### 4.6 PM skill priority hierarchy — MVP

Add to `templates/skills/project-manager/SKILL.md`:

> When the manifest, a command doc, a template, and a reference doc
> disagree:
>
> 1. `manifest.yaml` is canonical for artifact ownership
>    (`produced_by` / `owned_by`).
> 2. Reference docs (`SCHEMA_*.md`, `VALIDATION.md`,
>    `WORKFLOWS_*.md`) are canonical for schema and phase-gate rules.
> 3. Command docs (`.claude/commands/*.md`) describe mechanics, not
>    intent.
> 4. Templates describe shape, not responsibility.
>
> If a command doc instructs you to produce an artifact the manifest
> says someone else owns, follow the manifest. File a comment on the
> command doc so the conflict gets fixed.

Foundational fix for "which source do I trust" without restructuring
the skill.

---

## 5. PM command surface

### 5.1 The naming rule

Three categories, one rule per category:

- **Entity-scoped commands** use `pm-<entity>-<verb>` — direct object
  is a specific keel entity.
- **Non-entity commands** use `pm-<verb>` — no specific entity in
  scope.
- **Interpretive commands** use `pm-<noun>` — return a state report
  on the project as a whole.

### 5.2 Final surface (17 commands)

**Entity-scoped (7):**

| Command | Purpose |
|---|---|
| `/pm-issue-close <key> [note]` | Close an issue with completion comment |
| `/pm-session-create <issue-key> [agent-type]` | Create a session for an issue |
| `/pm-session-launch <session-id>` | Transition session to queued, verify readiness, write handoff comment |
| `/pm-session-check <session-id>` | Readiness punch list — what blocks launch |
| `/pm-session-progress [focus]` | Aggregate status across active sessions |
| `/pm-project-create <name> [--copy-nodes=...] [--path=...]` | Create a new project; auto-links if workspace context detected |
| `/pm-project-sync` | Pull from workspace, mediate merges, push |

**Non-entity verbs (7):**

`/pm-scope`, `/pm-rescope`, `/pm-triage`, `/pm-edit`, `/pm-review`,
`/pm-validate`, `/pm-lint`

**Interpretive (3):**

`/pm-status`, `/pm-agenda`, `/pm-graph`

### 5.3 Renames and removals

| Was | Now | Reason |
|---|---|---|
| `pm-handoff` | `pm-session-create` + `pm-session-launch` | Conflated two tasks |
| `pm-close` | `pm-issue-close` | Inconsistent (no entity prefix) |
| `pm-update` | `pm-edit` | "Update" overloaded with node update |
| `pm-plan` | (removed) | Confusingly named; users run `keel plan` directly |

### 5.4 CLI consequence

Drop the proposed `keel workspace new-project` command. Extend
`keel init` instead:

```
keel init <name> [--workspace <path>] [--copy-nodes=ID,ID]
```

`keel init` is already the canonical project-creation verb. Keep
one verb, add workspace-awareness as flags. If cwd resolves under a
workspace root, `--workspace .` is auto-inferred (unless
`--no-workspace`).

### 5.5 Branch naming convention

Per-session, not per-issue. A session = one branch = one PR. Issues
contained in a session appear in commits and PR description, not the
branch.

**Format:**

```
<type>/<session-slug>
```

- `<type>` — one of `feat`, `fix`, `refactor`, `docs`, `chore`, `test`.
  Derived from the **primary issue** (first item in
  `session.yaml.issues[]`)'s `kind` field, or explicit via
  `session.yaml.kind` override.
- `<session-slug>` — session ID with `session-` prefix stripped.

**Examples:**

| Session ID | Primary issue kind | Branch |
|---|---|---|
| `session-infra-gcs` | feat | `feat/infra-gcs` |
| `session-correct-sort-order` | fix | `fix/correct-sort-order` |
| `session-extract-session-store` | refactor | `refactor/extract-session-store` |

**Rules:**

- One branch per session. Same branch name across all repos in a
  multi-repo session.
- No personal prefixes (`maia/`, `claude/`).
- Length ≤ 60 chars. Lowercase. Hyphens only.

**Enforcement:**

- `handoff.yaml.branch` validated against pattern at session launch
- `keel lint handoff` flags malformed branch names
- `keel session derive-branch <session-id>` emits the canonical name
- New skill reference: `templates/skills/project-manager/references/BRANCH_NAMING.md`

**PR mapping:**

- 1 session = 1 branch = 1 PR
- PR title: `<type>(<session-slug>): <session summary>`
- PR description lists each contained issue with its resolution

---

## 6. End-to-end workflows

### 6.1 Workflow A — Create a project linked to a workspace

```
/pm-project-create customer-portal --copy-nodes=auth-system,event-schema-v2
```

Agent:

1. Detects workspace context (cwd under workspace root, or
   `--workspace` flag)
2. Runs `keel init customer-portal --workspace ../seido-workspace --copy-nodes=auth-system,event-schema-v2`
3. Reports:

```
✓ Scaffolded ../customer-portal/ (keel init defaults applied)
✓ Linked bidirectionally to workspace seido
✓ Copied 2 nodes (origin=workspace, scope=workspace, workspace_sha=a3f2b1c):
    - auth-system
    - event-schema-v2

Next: cd ../customer-portal && /pm-scope
```

Standalone projects without `--workspace` continue to work as today.

### 6.2 Workflow B — Sync a project with its workspace

```
/pm-project-sync
```

**CLI mechanical phase** (auto-applies trivial cases, generates
briefs for non-trivial):

```
$ keel workspace pull
Fetching workspace state (HEAD: d7e8f9a, 3 ahead of local)...
Auto-merged (2): auth-system, event-schema-v2
Needs agent resolution (1): related-service
  → brief: .keel/merge-briefs/related-service.yaml
  → draft applied to nodes/related-service.yaml

Exit 10: merges pending.
```

**Agent mediation phase:** Reads
`.keel/merge-briefs/related-service.yaml` containing structured
context (`base_version`, `ours_version`, `theirs_version`,
`field_diffs[]` with status per field, `auto_merged_fields`,
`hints`). Reasons about each field-level diff using project context
and node semantics. Edits `nodes/related-service.yaml` to the
resolved form.

```
$ keel workspace merge-resolve related-service
✓ validated
✓ workspace_sha updated to d7e8f9a
✓ merge brief deleted
```

**Push phase:**

```
$ keel workspace push
  auth-system: fast-forward (local changes apply cleanly)
  webhook-handler: promotion (new canonical node)

Created workspace commit e9f0a1b
2 nodes pushed successfully.
```

**One-way variants:** `/pm-project-sync --pull-only` or
`--push-only`.

### 6.3 Workflow C — Create and launch a session

Replaces ambiguous old `/pm-handoff`. Two-step explicit flow.

**Step 1 — create:**

```
/pm-session-create AUTH-42 backend-coder
```

Agent:

1. Reads `issues/AUTH-42/issue.yaml`, verifies status, no blockers
2. Allocates session key via `keel next-key --type session`
3. Creates `sessions/session-auth-42-setup/` with `session.yaml`,
   `plan.md`
4. Derives branch: `keel session derive-branch session-auth-42-setup`
   → `feat/auth-42-setup`
5. Writes `handoff.yaml` with branch, open_questions,
   context_to_preserve

```
✓ Session session-auth-42-setup created
  branch: feat/auth-42-setup
  handoff.yaml ready (1 open question)
  state: planned

Run /pm-session-check session-auth-42-setup to verify readiness.
Run /pm-session-launch session-auth-42-setup when ready.
```

**Step 2 — launch:**

```
/pm-session-launch session-auth-42-setup
```

Agent runs internal readiness check, then:

```
Readiness:
  ✓ Required planning artifacts (plan.md) present per manifest.yaml
  ✓ No unresolved blockers on AUTH-42
  ✓ Branch set + valid per convention: feat/auth-42-setup
  ✓ handoff.yaml populated (open_questions: 1, context_to_preserve: 3)
  ✓ Workspace context fresh (no stale workspace-origin nodes)

Transitioning: planned → queued
Writing handoff comment
✓ Session launched to backend-coder.
```

No artifact creation at launch — task-checklist is owned by execution
agent per `manifest.yaml.owned_by: execution-agent`.

### 6.4 Workflow D — Readiness check before launch

```
/pm-session-check session-auth-42-setup
```

Returns punch list without state transition:

```
Readiness report for session-auth-42-setup:

  ✓ State is planned (launch-eligible)
  ✓ Required planning artifacts per manifest.yaml:
      - plan.md: present
  ✗ Blockers:
      - AUTH-42 is blocked_by AUTH-41 (status: in_progress)
  ✗ handoff.yaml missing field: branch
  ⚠ Workspace context: auth-system is behind HEAD (workspace updated 2 days ago)
    → Run /pm-project-sync to refresh before launching.

2 must-fix, 1 warning. Not launch-ready.
```

### 6.5 Workflow E — Close an issue

```
/pm-issue-close AUTH-42 "Delivered as part of session-auth-42-setup. Unblocks AUTH-43, AUTH-44."
```

Agent:

1. Verifies AUTH-42 is not already closed
2. If associated session, verifies completion artifacts present
3. Transitions issue: `in_progress` → `done`
4. Writes completion comment
5. Validates, commits

```
✓ AUTH-42 closed
✓ Completion comment written
✓ Validation clean
✓ Unblocked: AUTH-43, AUTH-44 (mentioned in closing comment)

Commit: close: AUTH-42
```

---

## 7. Error cases and validation

### 7.1 Workspace binding errors

```
ERROR project_unlinked_workspace: project.yaml references workspace at
  ../seido-workspace but that path does not exist (missing workspace.yaml).
  fix_hint: `keel workspace link <correct-path>` or `keel workspace unlink`.
```

```
$ keel workspace list
✓ kbp     kb-pivot         ../project-kb-pivot
✗ kui     keel-ui-init     ../project-keel-ui-init  (path not found)
1 orphan. Run `keel workspace prune --force` to remove from registry.
```

Schema version mismatch (workspace.yaml.schema_version > supported):
hard error, blocks all workspace ops until keel is upgraded.

### 7.2 Node sync errors

- **Missing node on copy** — partial-success report, exits with count
- **ID collision on promote** — refuses with three options (rename,
  fork, --force-replace)
- **`workspace_sha` references missing commit** (workspace history
  rewritten) — refuses pull, suggests fork or `--force-reset`
- **Fork of non-workspace node** — error, fork applies only to
  workspace-origin nodes
- **Workspace node deleted while project has copy** — info, offers
  fork-to-keep or delete-to-accept

### 7.3 Merge resolution errors

- **Resolved node fails validation** — brief preserved, agent fixes
  and retries
- **Unresolved briefs blocking push** — push refuses, points to
  `/pm-project-sync`
- **Brief malformed** — directs agent to delete brief and re-pull

### 7.4 Concurrent operations

Reuses v0.5's `project_lock` (fcntl-based). Exponential backoff to
10s, then `lock_timeout` error with stale-lock cleanup guidance
(stale = mtime > 60s, existing v0.5 behaviour).

### 7.5 Schema validation additions

| Code | Target | Severity |
|---|---|---|
| `workspace_schema/version_unsupported` | workspace.yaml | error |
| `workspace_schema/projects_duplicate_slug` | workspace.yaml | error |
| `workspace_schema/projects_path_missing` | workspace.yaml | warning |
| `node_schema/origin_required` | every node | error |
| `node_schema/scope_required` | every node | error |
| `node_schema/workspace_sha_required` | `origin: workspace` nodes | error |
| `node_schema/workspace_sha_forbidden` | `origin: local` nodes | error |
| `manifest_schema/produced_by_valid` | manifest.yaml | error |
| `manifest_schema/owned_by_valid` | manifest.yaml | error |
| `manifest_schema/phase_ownership_consistent` | manifest.yaml | warning |
| `handoff_schema/branch_format` | handoff.yaml | error at launch, warning at validate |
| `handoff_schema/required_at_queued` | session in queued state | error |

All additions documented in
`templates/skills/project-manager/references/VALIDATION.md`.

### 7.6 Lint rules

| Rule | Stage | Severity |
|---|---|---|
| `lint/stale_workspace_nodes` | scoping, handoff | warning |
| `lint/unresolved_merge_briefs` | handoff | error |
| `lint/unpushed_promotion_candidates` | scoping | info |
| `lint/branch_convention` | handoff | error |
| `lint/gap_analysis_row_density` | scoping | warning |
| `lint/issue_body_orphan_concepts` | scoping | warning |
| `lint/session_stale` | session | warning (>3 days in implementing) |

Lint exits 0/1/2 on info/warning/error.

### 7.7 Command deprecation path

During v0.6:
- Old names (`pm-handoff`, `pm-close`, `pm-update`, `pm-plan`) emit
  deprecation notice and forward where unambiguous
- `pm-handoff` with an issue-key emits a specific error pointing at
  `pm-session-create` + `pm-session-launch`

After v0.7: old names removed. Migration tooling identifies tracked
script invocations.

### 7.8 Unrecoverable states

Three states require human intervention; v0.6 reports clearly with
runbook references:

- Workspace repo corrupted/unpullable (broken `.git/`)
- `workspace_sha` behind a force-pushed/rewritten history
- Cyclic schema_version requirement (workspace requires keel v0.7,
  keel wants to downgrade workspace to v0.6)

---

## 8. Testing strategy

Reuses v0.5 patterns: pytest, `save_test_*` store-based fixtures,
manual YAML for parser edge cases, subprocess pattern for
concurrency. Net new test count: ~120 across the bundle.

### 8.1 Unit tests — workspace core

| Module | Tests |
|---|---|
| `core/workspace.py` (paths, registry helpers) | 8 |
| `core/workspace_sync.py` (3-way merge engine) | 12 |
| `core/merge_brief.py` (brief generator) | 8 |
| `core/branch_naming.py` | 6 |
| `models/workspace.py` (Pydantic) | 5 |
| `models/handoff.py` (Pydantic) | 5 |

### 8.2 Unit tests — bundled PM improvements

| Module | Tests |
|---|---|
| `models/manifest.py` (produced_by/owned_by) | 6 |
| `core/linter.py` (per-rule heuristics) | 14 |
| `cli/session.py` (check, progress) | 8 |
| `cli/issue.py::close` | 4 |

### 8.3 Integration tests

- `test_workspace_create_and_link.py`
- `test_workspace_sync_happy.py`
- `test_workspace_sync_conflict.py`
- `test_workspace_promote_collision.py`
- `test_workspace_fork_then_workspace_evolves.py`
- `test_workspace_node_deleted_upstream.py`
- `test_session_lifecycle_with_workspace.py`
- `test_standalone_project_unchanged.py` (regression)
- `test_validate_fix_concurrent_workspace.py` (5 parallel pushes)

### 8.4 Slash command tests

- `test_slash_frontmatter.py` — every `pm-*.md` has valid frontmatter
- `test_slash_no_deprecated_refs.py` — no body references removed
  commands or CLI verbs
- `test_slash_naming_convention.py` — entity-prefixed names use
  allowed entity set
- `test_slash_deprecation_forwards.py` — old names emit notice +
  forward

### 8.5 Migration verification

For each of `kb-pivot`, `graph-ui-v2`, `project-keel-ui-init`:

- Apply v0.6 schema additions; verify nodes get default
  `origin: local, scope: local`
- `keel validate --strict` passes — projects valid v0.6 standalone
- Optionally link to a fresh workspace; verify bidirectional registry
- `keel lint scoping` reports honestly; no false positives on legacy
  content
- All v0.5 slash commands continue to function; deprecated ones emit
  notice

### 8.6 Property-based tests

- Branch convention parser: hypothesis-generated strings, valid
  patterns parse / invalid reject with specific codes
- Merge brief generator: synthesized node pairs with random field
  overlaps; assert briefs always (a) parse, (b) reconcile back to
  base/ours/theirs

### 8.7 Explicitly not tested

- Real agent reasoning quality on merge briefs (requires LLM run;
  test the interface, not judgment)
- UI integration with workspace (out of v0.6 scope)
- Remote workspace URLs (deferred)

### 8.8 Coverage gates

- All new validator rules: ≥1 passing + ≥1 failing fixture
- All new lint rules: ≥1 passing + ≥1 failing fixture
- Concurrent push/pull: 100 iterations with no flakes
- All three test projects migrate cleanly and pass `keel validate
  --strict` post-migration
- Test count grows ~512 → ~630 (+118 net)

### 8.9 CI pipeline updates

- New job: `pytest tests/unit/test_workspace_*` (parallelizable)
- New job: `pytest tests/integration/test_workspace_*` (sequential,
  uses tmp dirs)
- Migration verification applied to all three test projects

---

## 9. Migration plan (high-level)

Detailed migration steps belong in the implementation plan. High-level
shape:

1. **v0.6 ships additive.** No project migration required to upgrade.
   Existing projects work standalone. Old slash command names emit
   deprecation notices but still function.

2. **Optional: create the seido workspace.**
   - `mkdir seido-workspace && cd seido-workspace && keel workspace init`
   - For each existing project: `cd ../<project> && keel workspace link ../seido-workspace`
   - Identify duplicated concepts across projects; promote canonical
     versions to workspace via `keel workspace promote`.

3. **Schema migration is automatic.** `keel validate` on a v0.5
   project running on v0.6 keel:
   - Adds `origin: local, scope: local` to every node
   - Adds `produced_by` / `owned_by` to manifest entries (uses
     defaults: pm for planning artifacts, execution-agent for
     implementation artifacts)
   - No content changes

4. **Slash command updates.** PM skill ships updated slash command
   files with new names. Deprecated names live alongside for one
   release. Skill init re-renders templates on `keel init` of any
   project.

5. **Verification** (per existing v0.5 pattern):
   - All three test projects pass `keel validate --strict` after
     upgrade
   - All three pass `keel lint scoping` without false positives on
     legacy content
   - Optional workspace creation + linking exercised manually as
     part of release validation

---

## 10. Open questions

None blocking. Implementation plan should resolve:

- **Exact merge brief location** — `.keel/merge-briefs/` (current
  proposal) vs. inline annotation in node files. Lean: separate
  brief files keep node files clean.
- **Lint thresholds** — concrete numbers for `gap_analysis_row_density`,
  `session_stale`. Lean: ship defaults (3 rows/issue, 3 days),
  allow override via `project.yaml.lint_config` later.
- **Workspace pre-commit hook** — should `keel workspace push`
  trigger workspace-side validation before committing? Lean: yes,
  same `keel validate` pattern as project-side.

---

## 11. Cross-references

- `docs/keel-plan.md` — original v0.1 plan; data model and ID system
- `docs/overarching-plan.md` — three-module package architecture
- `docs/keel-core-features.md` — current feature inventory
- `docs/backlog.md` — deferred features (hybrid YAML+markdown,
  cross-project refs, etc.)
- `templates/skills/project-manager/SKILL.md` — PM skill that gains
  workspace awareness
- `templates/skills/project-manager/references/VALIDATION.md` — error
  code reference (extends with workspace codes)
- `templates/skills/project-manager/references/BRANCH_NAMING.md` —
  new reference shipping in v0.6
