# Workflow Actions Reference

Canonical reference for every workflow, status, transition, and supporting CLI
command. Updated when `templates/workflow.yaml.j2` changes.

`tripwire validate` enforces every invariant declared here. If an agent makes
a change that diverges from what's documented, validate flags it.

In v0.13 the live template (`src/tripwire/templates/workflow.yaml.j2`)
carries `coding-session` as the executor-driven workflow plus the 10
other workflow blocks (pm-scoping, pm-triage, pm-incremental-update,
project-maintenance, pm-monitor, code-review, inbox-handling,
pr-lifecycle, phase-advancement, issue-closure, concept-freshness) as
**reference declarations**. Step 7 (v0.13.1) restored these blocks
into the live template and added an `instance:` block on every
workflow so the runtime contract (storage path, status field, status
enum) is declared uniformly. They remain executor-free — only
`coding-session` is wired to `tripwire.core.workflow.transitions` —
but `tripwire validate` lints them and the renderer can draw them.
The historical pre-v0.13.1 view is preserved verbatim under
`docs/workflows/reference-only-workflows.md`.

---

## Workflows

### coding-session (live, executor-driven)

The lifecycle of a coding agent's work on an issue. The executor
(`tripwire.core.workflow.transitions`) is the sole writer of
`session.status`; every direct mutation routes through
`execute_transition` with a route id.

#### Statuses

| Status | Terminal | Routes out |
|---|---|---|
| planned | no | queued, abandoned |
| queued | no | executing, abandoned |
| executing | no | in_review, paused, failed, abandoned |
| in_review | no | verified, executing (changes requested), abandoned |
| verified | no | completed, in_review, abandoned |
| completed | yes | paused (reopen) |
| paused | no | executing, queued, completed, abandoned |
| failed | no | executing, abandoned |
| abandoned | yes | — |

#### Transitions

The table enumerates every route declared in the `coding-session:`
block. "Pre-CLI agent procedure" lists the Layer-1/Layer-2 CLI
commands the agent runs *before* the transition so the route's
tripwires (or implicit contract) can succeed. The transition itself
is a thin gate-and-flip.

| Route id | from → to | Kind | CLI | Pre-CLI agent procedure |
|---|---|---|---|---|
| `session-create` | source:issue → planned | forward | `tripwire transition coding-session <sid> planned` (issued by `/pm-session-create`) | PM scopes the session, writes the session.yaml + plan.md + verification-checklist.md skeleton. |
| `planned-to-queued` | planned → queued | forward | `tripwire transition coding-session <sid> queued` | `tripwire session queue add <sid> [--promote-issues]` (readiness check); plan.md + verification-checklist.md must be complete. |
| `queued-to-executing` | queued → executing | forward | `tripwire transition coding-session <sid> executing` (typically driven through `tripwire session spawn <sid>`) | `tripwire session spawn <sid>` (creates worktrees + skills + CLAUDE.md, starts the runtime). |
| `executing-to-in_review` | executing → in_review | forward | `tripwire transition coding-session <sid> in_review` | Coding agent records every artifact in `controls.tripwires` (diff, task-checklist.md, self-review.md, recommended-testing-plan.md, post-completion-comments.md, developer.md, tripwire-pr, project-pr); rebase PT branch onto origin/main. |
| `review-approved` | in_review → verified | forward | `tripwire transition coding-session <sid> verified` (issued by `/pm-session-review`) | Independent code-review evidence present (`pr_review.yaml`); verifier writes `verified.md`. |
| `review-changes-requested` | in_review → executing | revert | `tripwire transition coding-session <sid> executing` (issued by `/pm-session-review`) | PM writes `pm-response.yaml` with the requested changes; `runtime_state.claude_session_id` + `worktrees` preserved. |
| `verified-to-in_review` | verified → in_review | revert | `tripwire transition coding-session <sid> in_review` | PM reverses verification (rare). Preserves runtime state. |
| `verified-to-completed` | verified → completed | forward | `tripwire transition coding-session <sid> completed` (issued by `/pm-session-complete`) | `tripwire session prepare-for-completion <sid>` (validate clean under selector → `flip-drafts-ready` → confirm every PR is MERGEABLE / MERGED). After the transition, PRs must be merged on origin/main. |
| `executing-to-paused` | executing → paused | side | `tripwire transition coding-session <sid> paused` (typically driven through `tripwire session pause <sid>`) | `tripwire session pause <sid>` — calls runtime.pause and flips status. Preserves runtime state. |
| `executing-to-failed` | executing → failed | side | (runtime-event-driven; runtime sets the status when its process exits unexpectedly) | None — emitted by the runtime, not a CLI command. Preserves runtime state. |
| `paused-to-executing` | paused → executing | forward | `tripwire transition coding-session <sid> executing` (typically driven through `tripwire session spawn <sid> --resume`) | `tripwire session normalise-branch <sid>` if the PR was squash-merged on origin/main; then `tripwire session spawn <sid> --resume` to re-launch the agent. |
| `failed-to-executing` | failed → executing | forward | `tripwire transition coding-session <sid> executing` (typically driven through `tripwire session spawn <sid> --resume`) | `tripwire session spawn <sid> --resume`. Preserves runtime state. |
| `paused-to-queued` | paused → queued | revert | `tripwire transition coding-session <sid> queued` | None — operator re-queues a paused session for later spawn. |
| `paused-to-completed` | paused → completed | revert | `tripwire transition coding-session <sid> completed` | None — rare "never mind, leave completed" path after a reopen the PM decides not to act on. |
| `completed-to-paused-reopen` | completed → paused | revert | `tripwire transition coding-session <sid> paused` (issued by `tripwire session reopen <sid>`) | `tripwire session reopen <sid> --reason="…" [--reset-acks]` — this command flips drafts back to draft, appends the PM follow-up stub to plan.md, optionally resets tripwire acks, and records the reopen audit entry. |
| `planned-to-abandoned` | planned → abandoned | side | `tripwire transition coding-session <sid> abandoned` (typically driven through `tripwire session abandon <sid>`) | `tripwire session abandon <sid>` — for `planned`, no runtime/PRs to tear down. |
| `queued-to-abandoned` | queued → abandoned | side | `tripwire transition coding-session <sid> abandoned` (typically driven through `tripwire session abandon <sid>`) | `tripwire session abandon <sid>` — no runtime yet; engagement closes on terminal. |
| `executing-to-abandoned` | executing → abandoned | side | `tripwire transition coding-session <sid> abandoned` (typically driven through `tripwire session abandon <sid>`) | `tripwire session prepare-for-abandon <sid>` (kill-runtime → close-prs → remove-worktrees), then `tripwire session abandon <sid>`. |
| `paused-to-abandoned` | paused → abandoned | side | `tripwire transition coding-session <sid> abandoned` (typically driven through `tripwire session abandon <sid>`) | `tripwire session prepare-for-abandon <sid>`, then `tripwire session abandon <sid>`. |
| `failed-to-abandoned` | failed → abandoned | side | `tripwire transition coding-session <sid> abandoned` (typically driven through `tripwire session abandon <sid>`) | `tripwire session prepare-for-abandon <sid>` (runtime is already dead but PRs/worktrees may still need teardown). |
| `in_review-to-abandoned` | in_review → abandoned | side | `tripwire transition coding-session <sid> abandoned` (typically driven through `tripwire session abandon <sid>`) | `tripwire session prepare-for-abandon <sid>` — close PRs, remove worktrees. |
| `verified-to-abandoned` | verified → abandoned | side | `tripwire transition coding-session <sid> abandoned` (typically driven through `tripwire session abandon <sid>`) | `tripwire session prepare-for-abandon <sid>` — late-stage abandon; still close PRs + worktrees. |

Side-effects historically declared via `route.side_effects:` (sweep
issues forward, rebase PT branch, flip drafts to ready/draft, kill
runtime, close PRs, remove worktrees, append PM follow-up, reset
acks) now live as Layer-1 / Layer-2 CLI wrappers and are run by the
agent before the transition. The executor still records audit /
telemetry / engagement-close on terminal flips, but does not
orchestrate external side-effects on the agent's behalf.

---

### Reference-only workflows (no executor coverage)

The following workflows shipped in `workflow.yaml.j2` through v0.12
as documentation of the surrounding PM/review/ops process. They have
no executor — no `WORKFLOW_ID` registered in
`tripwire.core.workflow.transitions`, no route ever drove a status
mutation through them — and are preserved verbatim under
`docs/workflows/reference-only-workflows.md`.

Routes for these workflows are being filled in by the agent
conversationally per the skill markdown; the tables below summarise
the statuses + named routes as declared in the reference doc.
`tripwire validate` does not gate transitions in these workflows
because the executor doesn't run them.

If you want to materialise any of these into an executable workflow,
the path is: register a `WORKFLOW_ID` in the executor module, add
the appropriate side-effect handlers in
`core/workflow/side_effects.py` (or keep the workflow side-effect-
free and rely on Layer-1 CLI wrappers the agent invokes), and wire
the routes with their tripwires.

#### pm-scoping (reference only)

| Status | Terminal | Routes out |
|---|---|---|
| intake | no | draft |
| draft | no | validate |
| validate | no | draft, publish |
| publish | yes | — |

| Route id | from → to | Kind | CLI |
|---|---|---|---|
| `scope-intake` | source:intent → intake | forward | conversational (`/pm-scope`) |
| `draft-scope` | intake → draft | forward | conversational (`/pm-scope`) |
| `validate-scope` | draft → validate | forward | `tripwire validate` |
| `scope-gap-loop` | validate → draft | return | conversational (`/pm-rescope`) |
| `publish-scope` | validate → publish | forward | conversational (`/pm-scope`) |

#### pm-triage (reference only)

| Status | Terminal | Routes out |
|---|---|---|
| intake | no | classify |
| classify | no | act |
| act | no | close |
| close | yes | — |

| Route id | from → to | Kind | CLI |
|---|---|---|---|
| `triage-intake` | source:inbox → intake | forward | conversational (`/pm-triage`) |
| `classify-item` | intake → classify | forward | conversational (`/pm-triage`) |
| `act-on-item` | classify → act | forward | conversational (`/pm-edit`) |
| `close-triage` | act → close | forward | conversational (`/pm-triage`) |

#### pm-incremental-update (reference only)

| Status | Terminal | Routes out |
|---|---|---|
| inspect | no | edit |
| edit | no | validate |
| validate | no | publish, edit |
| publish | yes | — |

| Route id | from → to | Kind | CLI |
|---|---|---|---|
| `inspect-update` | source:change-request → inspect | forward | conversational (`/pm-edit`) |
| `apply-update` | inspect → edit | forward | conversational (`/pm-edit`) |
| `validate-update` | edit → validate | forward | `tripwire validate` |
| `fix-update-loop` | validate → edit | return | conversational (`/pm-edit`) |
| `publish-update` | validate → publish | forward | conversational (`/pm-issue-close`) |

#### project-maintenance (reference only)

| Status | Terminal | Routes out |
|---|---|---|
| inspect | no | report |
| report | yes | — |

| Route id | from → to | Kind | CLI |
|---|---|---|---|
| `status-report` | source:project → inspect | forward | conversational (`/pm-status`) |
| `agenda-report` | inspect → report | forward | conversational (`/pm-agenda`) |
| `graph-report` | inspect → report | side | conversational (`/pm-graph`) |
| `validate-report` | inspect → report | side | `tripwire validate` |
| `sync-project` | inspect → report | side | conversational (`/pm-project-sync`) |

#### pm-monitor (reference only)

| Status | Terminal | Routes out |
|---|---|---|
| scan | no | classify |
| classify | no | dispatch, idle |
| dispatch | no | idle |
| idle | no | scan |
| stopped | yes | — |

| Route id | from → to | Kind | CLI |
|---|---|---|---|
| `monitor-tick` | idle → scan | forward | conversational (`/pm-monitor`) |
| `scan-to-classify` | scan → classify | forward | conversational |
| `dispatch-launch-session` | classify → dispatch | forward | conversational |
| `dispatch-relaunch` | classify → dispatch | forward | conversational |
| `dispatch-review` | classify → dispatch | forward | conversational |
| `dispatch-triage` | classify → dispatch | forward | conversational |
| `dispatch-idle` | classify → idle | side | conversational |
| `dispatch-to-idle` | dispatch → idle | forward | conversational |

#### code-review (reference only)

| Status | Terminal | Routes out |
|---|---|---|
| received | no | gate-check |
| gate-check | no | independent-reviews |
| independent-reviews | no | synthesis |
| synthesis | no | node-reconcile, relaunch |
| node-reconcile | no | merge |
| merge | yes | — |
| relaunch | yes | — |

| Route id | from → to | Kind | CLI |
|---|---|---|---|
| `pr-pair-received` | source:session.in_review → received | forward | conversational |
| `pass-gate` | received → gate-check | forward | conversational |
| `enter-reviews` | gate-check → independent-reviews | forward | conversational |
| `enter-synthesis` | independent-reviews → synthesis | forward | conversational |
| `route-to-merge` | synthesis → node-reconcile | forward | conversational (`/pm-session-review`) |
| `route-to-relaunch` | synthesis → relaunch | return | conversational (`/pm-session-review`) |
| `do-merge` | node-reconcile → merge | forward | conversational (PR merges via `gh`) |

#### inbox-handling (reference only)

| Status | Terminal | Routes out |
|---|---|---|
| pending | no | triaged |
| triaged | no | resolved |
| resolved | yes | — |

| Route id | from → to | Kind | CLI |
|---|---|---|---|
| `inbox-receive` | source:inbox → pending | forward | conversational |
| `inbox-triage` | pending → triaged | forward | conversational (`/pm-edit`) |
| `inbox-resolve` | triaged → resolved | forward | conversational |

#### pr-lifecycle (reference only)

| Status | Terminal | Routes out |
|---|---|---|
| draft | no | ready |
| ready | no | reviewing |
| reviewing | no | approved, rejected |
| approved | no | merged |
| merged | yes | — |
| rejected | yes | — |

| Route id | from → to | Kind | CLI |
|---|---|---|---|
| `pr-open` | source:branch → draft | forward | `gh pr create --draft` |
| `pr-ready` | draft → ready | forward | `tripwire gh pr-ready <num>` |
| `pr-enter-review` | ready → reviewing | forward | conversational |
| `pr-approve` | reviewing → approved | forward | conversational |
| `pr-reject` | reviewing → rejected | return | conversational |
| `pr-merge` | approved → merged | forward | `gh pr merge` |

#### phase-advancement (reference only)

| Status | Terminal | Routes out |
|---|---|---|
| scoping | no | scoped |
| scoped | no | executing |
| executing | no | reviewing |
| reviewing | yes | — |

| Route id | from → to | Kind | CLI |
|---|---|---|---|
| `advance-to-scoped` | scoping → scoped | forward | conversational (`/pm-phase`) |
| `advance-to-executing` | scoped → executing | forward | conversational (`/pm-phase`) |
| `advance-to-reviewing` | executing → reviewing | forward | conversational (`/pm-phase`) |

#### issue-closure (reference only)

| Status | Terminal | Routes out |
|---|---|---|
| planned | no | queued, deferred, abandoned |
| queued | no | executing, deferred, abandoned |
| executing | no | in_review, deferred, abandoned |
| in_review | no | verified, executing (return), abandoned |
| verified | no | completed, in_review (return), abandoned |
| completed | yes | — |
| abandoned | yes | — |
| deferred | no | planned, abandoned |

| Route id | from → to | Kind | CLI |
|---|---|---|---|
| `issue-plan-to-queue` | planned → queued | forward | conversational |
| `issue-queue-to-execute` | queued → executing | forward | conversational |
| `issue-execute-to-review` | executing → in_review | forward | conversational |
| `issue-review-to-verified` | in_review → verified | forward | conversational |
| `issue-verified-to-completed` | verified → completed | forward | conversational (`/pm-issue-close`) |
| `issue-review-back-to-execute` | in_review → executing | return | conversational |
| `issue-verified-back-to-review` | verified → in_review | return | conversational |
| `issue-abandon-from-*` (5 routes) | {planned, queued, executing, in_review, verified} → abandoned | terminal | conversational |
| `issue-defer-from-*` (3 routes) | {planned, queued, executing} → deferred | side | conversational |
| `issue-deferred-back-to-planned` | deferred → planned | forward | conversational |
| `issue-deferred-to-abandoned` | deferred → abandoned | terminal | conversational |

Note: although `issue-closure` is reference-only as a self-contained
workflow, `tripwire transition issue-closure <key> <target>` is used
by `tripwire session sweep-issues-forward` to drive issues through
their status field. The 8-status enum + 17 routes here mirror the
canonical issue lifecycle; it is also the source of truth for
`tripwire validate`'s `status/unreachable` check
(`core/status.build_issue_transitions`).

---

## CLI commands by layer

### Core

| Command | Purpose |
|---|---|
| `tripwire transition <workflow> <instance> <target>` | Atomic status flip with validation. The single writer of status fields. Resolves the route in `workflow.yaml` from `(current, target)`, runs the route's gate (tripwires, JIT prompts, prompt-checks, consumed artifacts), and atomically flips the status. |
| `tripwire transition <instance> <target>` | Legacy two-arg form — implies `workflow=coding-session`. |
| `tripwire validate` | Run all validators across the project. Single accountability surface. Strict-by-default (warnings are errors). Exit 0 = clean, 1 = warnings, 2 = errors. |
| `tripwire validate --select <ID>+` | Validate a specific subtree (forward, backward, or N-hop) — `ID+`, `+ID`, `ID+N`, or `tag:NAME`. |
| `tripwire validate --fix` | Auto-fix the defined subset of issues (timestamps, UUIDs, etc.). |
| `tripwire validate --format json` | Emit the full report serialised to the spec's JSON schema. |
| `tripwire validate --count` | Print just the error count and exit. |
| `tripwire validate --quiet-heuristics` | Drop heuristic findings whose suppression marker exists. |
| `tripwire validate --no-heuristics` | Skip heuristic-class findings entirely. |
| `tripwire validate --heuristics-as-tripwires` | Promote every fired heuristic to error (CI gating). |
| `tripwire project brief` | Print project config, active enums, templates, next-available IDs — the agent's first call on every session. |

### Layer 1 — Individual operation wrappers

| Command | Purpose |
|---|---|
| `tripwire git rebase-pt <wt-path>` | Rebase a PT branch onto `origin/main` with our defaults. |
| `tripwire gh pr-ready <num>` | Mark a PR ready for review. |
| `tripwire gh pr-ready-undo <num>` | Flip a ready PR back to draft. |
| `tripwire gh pr-close <num>` | Close a PR (no merge). |
| `tripwire session kill-runtime <sid>` | SIGTERM the session's runtime pid. Best-effort: no recorded pid is a clean no-op; ESRCH is swallowed. |
| `tripwire session close-prs <sid>` | Close any open PR across the session's recorded worktrees. Best-effort. |
| `tripwire session remove-worktrees <sid>` | Remove every recorded worktree directory for the session. Best-effort. |
| `tripwire session normalise-branch <sid>` | For each worktree whose PR was squash-merged, `git reset --hard origin/main`. Idempotent. |
| `tripwire session flip-drafts-ready <sid>` | Flip every draft PR on the session's worktrees to ready-for-review. |
| `tripwire session flip-drafts-draft <sid>` | Flip every ready PR on the session's worktrees back to draft. |
| `tripwire session followup-stub <sid> --reason="…"` | Append the canonical "PM follow-up" section to the session's `plan.md`. Idempotent. |

### Layer 2 — Common combos

| Command | Chains |
|---|---|
| `tripwire session prepare-for-completion <sid>` | `validate --select <sid>` → `flip-drafts-ready` → confirm each PR is MERGEABLE/MERGED via `gh pr view`. Exit 0 only when all three pass. Idempotent. |
| `tripwire session prepare-for-abandon <sid>` | `kill-runtime` → `close-prs` → `remove-worktrees`. Per-step failures collected; exits 1 with a per-step summary if any step hard-failed. |
| `tripwire session sweep-issues-forward <sid>` | Per member issue, run `tripwire transition issue-closure <key> <target>` to drive the issue forward to match the session's status (target derived from `sweep_target_for(session.status)`). |

### Layer 3 — Skill commands (slash commands)

Documented in the skill markdown at
`src/tripwire/templates/skills/project-manager/SKILL.md` (and the
sibling skills `backend-development/`, `verification/`,
`agent-messaging/`). The slash commands wrap Layer-1 / Layer-2 CLI
calls with agent reasoning + recovery procedures.

The PM slash commands relevant to the live `coding-session` workflow
are:

- `/pm-session-create` — author the session, plan.md, verification
  checklist.
- `/pm-session-queue` — readiness check + transition planned → queued.
- `/pm-session-spawn` — `tripwire session spawn`, queued → executing.
- `/pm-session-review` — PM review; in_review → verified (approve) or
  in_review → executing (request changes).
- `/pm-session-complete` — `prepare-for-completion` + verified →
  completed.

Out-of-band command-driven transitions on the side-state edges
(`pause`, `abandon`, `reopen`, `--resume`) are invoked through the
session subcommands (`tripwire session pause/abandon/reopen/spawn
--resume`) rather than dedicated slash commands.

---

## How invariants get enforced

Every validator listed in a route's `controls.tripwires:` runs at
transition time. If any fail, the transition is rejected with the
findings; the agent MUST address the findings before retrying.

Every validator is also runnable via `tripwire validate` outside the
transition path — agents and humans use it for project-wide audits.

The validator catalog is sourced from
`src/tripwire/core/validator/checks/` and
`src/tripwire/core/validator/lint/`. Adding a new validator is:
write a `check(ctx)` function, register it in the appropriate
`_CHECKS` list, reference its id from a route. Three orthogonal
extension points:

- **New skill (slash command)** — wrap CLI under
  `src/tripwire/templates/skills/<name>/`.
- **New workflow / route / status** — declare in
  `src/tripwire/templates/workflow.yaml.j2`. Register the workflow
  id in the executor only if it needs to drive a status mutation.
- **New invariant** — add a `check(ctx)` function, register in the
  relevant `_CHECKS` list, reference from the route's
  `controls.tripwires:`.
