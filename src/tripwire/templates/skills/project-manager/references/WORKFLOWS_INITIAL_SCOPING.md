# Workflow: Initial Scoping

> **Compliance reminder.** `tripwire validate` is your accountability
> surface. Run it after every change. Exit code 0 → proceed. Non-zero
> → STOP and address findings. **You MUST NOT skip validation.**

Transform raw planning docs into a fully scoped project: issues, concept
nodes, sessions, and session plans that pass validate and are ready for
delegation.

## Precondition

A freshly-init'd `tripwire` directory. `tripwire project init` creates an empty
`./plans/`; the user drops raw planning docs there before invoking
scoping. If `./plans/` is empty or missing, scope from user intent
alone.

**Project-tracking repo git remote (v0.7.4+).** For parallel sessions,
configure a remote (`git remote -v` shows ≥1 entry). With a remote,
`session spawn` cuts a per-session `proj/<slug>` worktree so parallel
agents don't race on `sessions/<id>/` or `issues/<KEY>/developer.md`
writes. No remote → shared-directory writes (pre-v0.7.4 behaviour).

## Before you start

Reread the "How you think about scope" section in SKILL.md — no target
count, no time budget, no subagents for writes. Those rules apply
without exception throughout this workflow.

## Procedure

### 1. Front-load context

Run:

```bash
tripwire project brief
```

Read the output. Note the `next issue key`, active enums, registered
repos, artifact manifest, orchestration pattern, and skill example
paths.

**Repos.** If the planning docs reference repositories not registered
in `project.yaml`, register them now. Edit `project.yaml` and add
each repo under `repos:` with its GitHub slug and optional local
clone path. Every issue must reference a registered repo.

If `brief` fails: read the error, fix the underlying file, re-run.

### 2. Read the planning docs

Read every `.md` under `./plans/` in full. If `./plans/` is empty or
missing, use the user's intent (passed via `$ARGUMENTS` to `/pm-scope`)
as your sole source.

If a file exceeds your read limit, chunk it. Don't skip sections. Don't
skim — you need every endpoint table, schema definition, infra
resource, migration step.

### 3. Read the canonical examples

Before writing any file, read at least:

- `examples/issue-fully-formed.yaml`
- `examples/issue-epic.yaml`
- `examples/node-endpoint.yaml`
- `examples/node-decision.yaml`
- `examples/session-planned.yaml`
- `examples/artifacts/plan.md`

The example files are the canonical truth. If your output doesn't look
like them, you're doing it wrong.

### 4. Write the scoping plan artifact

**This step produces a file, not a mental sketch.** Use the `Write`
tool to create:

```
plans/artifacts/scoping-plan.md
```

Structure:

```markdown
# Scoping plan

## Epics
- Epic 1: [title] — [one-sentence scope]
- Epic 2: ...

## Issues
For each issue:
- [title] — parent: [epic], repo: [slug], executor: [ai|human],
  priority: [H/M/L], blocked_by: [list], concept refs: [node-ids]

## Concept nodes
For each node:
- [slug-id] — type: [endpoint|model|config|decision|contract|...],
  referenced by: [issue list]

## Sessions
For each session:
- [slug-id] — issues: [list], blocked_by_sessions: [list],
  estimated_size: [S/M/L]
```

**This file is consumed by step 5.** If it doesn't exist, step 5
cannot proceed.

### 5. Allocate IDs and UUIDs

Read `plans/artifacts/scoping-plan.md`. For each issue listed, run:

```bash
tripwire project next-key --type issue --count N
```

where N is the number of issues. Collect the allocated keys.

For UUIDs, run:

```bash
tripwire uuid --count N
```

where N is the total entity count (issues + nodes + sessions). Save
the output. Assign UUIDs to entities from this list as you write
files. **You MUST NOT hand-craft UUIDs** — the validator checks RFC
4122 v4 bits.

Node and session ids are slugs you choose (lowercase, letter-first,
hyphenated). Session ids should be descriptive: `storage-adapter-impl`,
`api-endpoints-core`, `frontend-shell`.

If any step fails: read the error, fix it, re-run. Do not invent IDs
to keep moving.

### 6. Write the files

Use the `Write` tool to create each file. Write in dependency order so
early files can be referenced by later ones:

1. **Concept nodes first** → `nodes/<id>.yaml`
2. **Epic issues** → `issues/<KEY>/issue.yaml`. Epics MUST have the
   `type/epic` label. Required body sections for epics: Context,
   Child issues, Acceptance criteria. Epics do NOT need Implements,
   Repo scope, Execution constraints, Test plan, Dependencies, or
   Definition of Done. See `examples/issue-epic.yaml`.
3. **Concrete issues** → `issues/<KEY>/issue.yaml`. Reference epics as
   `parent`, reference concept nodes via `[[node-id]]` in the body.
   Required body sections: all 9 (Context, Implements, Repo scope,
   Requirements, Execution constraints, Acceptance criteria, Test
   plan, Dependencies, Definition of Done).
4. **Sessions** → `sessions/<id>/session.yaml` (directory, not flat
   file). Each session gets its own directory. **The `status:` field
   starts at `planned`. Do not set later statuses by hand — use
   `tripwire transition coding-session <sid> <target>` once the
   session is ready to advance.**
5. **Session plans** → `sessions/<id>/plan.md` for every session,
   using the step-by-step template from `examples/artifacts/plan.md`.

**Issue depth.** Every issue will be read by an execution agent that
has NOT read the planning docs and does NOT share your context.
Default to more detail, not less. If a concept, endpoint, schema, or
decision is relevant to the issue, write it into the issue body
explicitly. The execution agent cannot infer what you know.

**Forward references.** Dangling `[[node-id]]` refs are always wrong
— create the node first, then the referrer. Dangling `blocked_by`
refs to issues you've allocated keys for but haven't written yet are
acceptable — they resolve when you write those issues in the next
batch.

#### Quality calibration checkpoint

Output measurably thins over a long run (24% character drop, 63%
reference drop between first and last 20 issues — see SKILL.md). After
every 20 concrete issues:

1. Reread your first 3 — note char count, `[[node-id]]` count,
   requirement specificity, test-plan completeness.
2. Reread your last 3. Compare on the same dimensions.
3. If the last 3 are thinner (shorter bodies, fewer refs, vaguer
   requirements, missing specifics from the docs), rewrite them
   against the first 3 as your standard. Don't rationalise ("simpler
   issues") — verify against the planning docs.
4. Run `tripwire validate`. Exit 0 → continue. Non-zero → STOP and
   fix.
5. Record the calibration in `plans/artifacts/compliance.md` under
   "Quality calibration checkpoints".

### 7. Red-green validation cycle

After every 3-5 files, run:

```bash
tripwire validate
```

Walk errors in order:

1. `schema/*` — fill placeholder fields with real values.
2. `ref/dangling` — create the target node or replace the ref.
3. `body/*` — fill missing body sections.
4. `enum/*` — fix invalid enum values.
5. `coverage/*` — investigate; these are warnings about semantic gaps.

Repeat until exit 0. Validate is structural only — completeness is
step 9 (gap analysis).

If any step fails repeatedly: read the validator finding fully, locate
the offending file, fix the root cause. Do not paper over by removing
fields.

### 8. Second-pass: node coverage

**Mandatory.** Steps 8-10 are not optional — deferral is cancellation.
Validate-clean ≠ scope complete.

Scan every issue body:

- Concept in prose (not `[[ref]]`) across 3+ issues → create a node,
  replace prose with `[[ref]]`.
- `[[node-id]]` referenced by only 1 issue → either the node is too
  narrow (merge) or other issues forgot to reference it (add refs).
- Issue with 0 `[[node-id]]` refs → not linked to the graph; add refs.

Run `tripwire node refs summary` for reference counts.

After every change in this pass: `tripwire validate`. Exit 0 →
continue. Non-zero → STOP and fix.

### 9. Gap analysis

The semantic completeness check validate cannot do. Skipping it ships
incomplete scope to the execution agent. Reread the planning docs —
don't work from memory.

Use the `Write` tool to produce `plans/artifacts/gap-analysis.md`:

**Planning doc → project coverage.** Reread every planning doc. For
each section, list every individual concrete deliverable (one
endpoint, migration step, UI page, infra resource, pipeline, schema
change). One row in the table per deliverable mapped to one issue.
`"KBP-17 through KBP-20 | Covered"` is a TOC, not a gap analysis —
list each issue separately. Missing deliverables → flag **GAP** and
create the issue.

**Planning doc internal coherence.** Do the docs contradict each
other? Does the API spec reference infra the infra spec doesn't
mention? Does the frontend depend on endpoints the API spec doesn't
list? Flag **INCONSISTENCY** and comment on the relevant issue.

**Project self-coherence.** Run `tripwire project agenda` and
`tripwire node graph --type concept`. Flag: issues with 0 node refs, nodes
with only 1 referrer, sessions with 0 issues, dependency cycles or
orphans.

For each gap, create the missing issue or node. For each
inconsistency, comment on the relevant issue. Run `tripwire validate`
after each addition.

### 10. Produce meta-artifacts

**Mandatory.** `compliance.md` is consumed by step 12; the validator
enforces it at `phase: scoped`. Use the `Write` tool to create three
files in `plans/artifacts/`:

1. **`scoping-verification.md`** — planning-doc sections → issues/nodes.
   Every section gets a mapping or an explicit "out of scope".
2. **`task-checklist.md`** — your PM task list: docs read, nodes
   created, issues created, sessions created, gap analysis done.
3. **`compliance.md`** — each workflow rule marked followed/deviated.
   Explain deviations.

### 11. Final validation + confirm shape

Run, in order:

```bash
tripwire validate
tripwire project status
tripwire project agenda --by status
tripwire node graph --type concept
tripwire node refs summary
```

Exit 0 on validate. Counts match your scoping plan. No orphan nodes.

If any disagrees with your scoping plan: investigate and fix before
advancing.

### 12. Advance phase + commit

Read `compliance.md`. Resolve any deviations or document justification
— do not commit with unresolved deviations. Replace
`<!-- status: incomplete -->` with `<!-- status: complete -->` in every
file under `plans/artifacts/`.

Set `phase: scoped` in `project.yaml` and re-run `tripwire validate`.
Missing or incomplete gap-analysis/compliance artifacts fail the gate.

One commit for the whole initial scoping (per `COMMIT_CONVENTIONS.md`).

**The project's own status changes** (e.g. `phase: scoping → scoped`)
go through `tripwire transition pm-scoping <project-id> <target>` when
that workflow is executor-driven. Today `pm-scoping` is reference-only
— set `phase:` in `project.yaml` and rely on the validator gate. Check
`docs/WORKFLOW_ACTIONS.md` for current executor coverage.

If validation still fails after phase advance: revert `phase:` to its
previous value, fix the underlying artifact, re-validate, then
advance.

## Scoping-specific red flags

The general rationalisations are in SKILL.md. Specific to scoping:

| Agent thought | Reality |
|---|---|
| "Enough issues for this project" | Planning docs define scope, not your intuition. |
| "Validate at the end, not per batch" | Validate after every 3-5 files; errors compound. |
| "This concept doesn't need a node" | 2+ issues / contract / interface → node. When in doubt, create. |
| "Plan later, issues first" | Plan artifact is consumed by step 5. First. |
| "Docs are ambiguous, I'll guess" | Stop. Ask. Wrong assumptions cascade. |
| "Skip gap analysis — validate passed" | Validate is structural; gap analysis is semantic. Both. |
| "I can track UUIDs in my head" | Use `tripwire uuid`. Validator catches hand-crafted. |
| "With more time I'd split this" | You have time. Split now. |

## See also

- `CONCEPT_GRAPH.md` — when to create a node.
- `VALIDATION.md` — error catalogue.
- `ANTI_PATTERNS.md` — full anti-pattern list.
- `WORKFLOWS_INCREMENTAL_UPDATE.md` — small surgical edits.
- `docs/WORKFLOW_ACTIONS.md` — every CLI command and transition.
