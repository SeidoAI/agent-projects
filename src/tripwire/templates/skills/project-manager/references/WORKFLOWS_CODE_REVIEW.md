# Workflow: Code Review

> **Compliance reminder.** `tripwire validate` is your accountability
> surface. Run it after every change. Exit code 0 → proceed. Non-zero
> → STOP and address findings. **You MUST NOT skip validation.**

Closes a coding session. The session produces a **PR pair** —
`tripwire-pr` (project tracking repo) and `project-pr` (code repo).
Both must land atomically; either alone leaves the project graph and
shipped code out of sync. v0.9 splits this cycle out of
`coding-session` so each station has its own controls and audit.

`code-review` is reference-only as a self-contained workflow today.
The session-status side (`in_review → verified → completed`, or
`in_review → executing` on relaunch) goes through the executor-driven
`coding-session` workflow. **All session status mutations go through
`tripwire transition coding-session <sid> <target>`** — never edit
`session.yaml.status` by hand.

## Trigger

`pm-monitor` fires `signal.session_pr_pair_open` when both PR URLs
are set on `session.yaml` and both PRs are in
`{open, ready_for_review}`; dispatch routes to
`code-review.received` (see `MONITOR_CRITERIA.md`).

## Stations

### `received`

Confirm the PR pair is present and live. Tripwires
`v_pr_pair_present`, `v_branch_alive`. Records PR URLs, branches,
head SHAs (pinning so downstream stations measure against the
review's starting commit).

### `gate-check`

1. Run `gh pr checkout <project-pr>`.
2. Run `tripwire validate` against the tripwire-pr branch. Exit 0 →
   continue. Non-zero → STOP, record findings, do not advance.
3. Walk the verification checklist
   (`templates/skills/verification/`).
4. Run `tripwire session review <id> --write-verified` → emits
   `docs/issues/<KEY>/verified.md` per closed issue.

`--write-verified` runs here because once branches merge or delete,
the per-issue evidence (diff ranges, test outputs, AC walk) cannot
be reconstructed. Tripwires `v_validate_passes_on_branch`,
`v_verified_md_written` — failing either halts before reviewers are
dispatched.

If any step fails: read findings, fix in place on the project-pr
branch, push, re-run from step 2.

### `independent-reviews`

Three parallel reads:

1. **Self-review.** PM reads the agent's four-lens self-review on
   the project-pr.
2. **Superpowers subagent.** PM dispatches per
   `superpowers-code-review.md`. Output:
   `<project>/sessions/<id>/reviews/superpowers.yaml`.
   Implementation lives outside this repo; tripwire only consumes
   the file.
3. **Codex.** PM comments `@codex` on the project-pr. Findings
   surface as PR comments; PM extracts to
   `<project>/sessions/<id>/reviews/codex.md`.

If a reviewer doesn't return, the PM proceeds and records the
absence in synthesis.

### `synthesis`

PM reads all three reviews end-to-end and uses the `Write` tool to
create `<project>/sessions/<id>/reviews/synthesis.md`: one row per
finding (severity, source, PM verdict accept / reject / defer), final
overall verdict (`merge` | `relaunch`).

Decision rule of thumb:

| Signal | Verdict |
|---|---|
| Any blocking finding not rejected with written rationale | relaunch |
| Any major finding outside `session.repo_paths` | relaunch |
| Self + superpowers clean, codex only nits | merge |
| Reviewers disagree on a major finding | PM is tiebreaker; rationale in synthesis |

Controls:

- JIT prompt `reviews-not-actually-read` (hidden, ack-required;
  aspirational id, stage 2 implements the ack). Forces the PM to
  confirm they actually read all three reviews.
- Heuristic `scope-creep-detected` (aspirational; hidden in stage
  2). Fires when project-pr touches paths outside
  `session.repo_paths`.
- Prompt-checks on outgoing routes: `pm-review` for the merge
  branch; `pm-session-reopen` for the relaunch branch.

### `node-reconcile`

Identify nodes the project-pr touches (via divergence callouts and
`verified.md`). For each: body diverges → update (shipped wins;
see `WORKFLOWS_NODE_RECONCILIATION.md`); concept with no node →
create it; source changed → rehash `source.content_hash`.

After each node touched: `tripwire validate`. Exit 0 → continue.
Non-zero → STOP and fix before merge.

Cross-link: `node-reconcile → concept-freshness.detected,
kind: triggers`. Reconciling before merge keeps the drift scoped
to the session that caused it.

### `merge` — terminal pass-state

1. Confirm `tripwire validate` is clean on the tripwire-pr branch.
2. Merge tripwire-pr.
3. Merge project-pr.
4. Run `tripwire session prepare-for-completion <sid>`. This chains
   `validate --select <sid>` → `flip-drafts-ready` → confirms each
   PR is MERGEABLE/MERGED via `gh pr view`. Exit 0 only when all
   three pass; idempotent.
5. Run `tripwire transition coding-session <sid> completed`.

Tripwires `v_no_stale_nodes_post_reconcile` (guards "PM said merge
but freshness scan still has open items"),
`v_done_implies_issue_artifacts_on_main` (guards "session done but
verified.md / closing comment never landed on main").

If `prepare-for-completion` fails: read its per-step output, address
the named failure (e.g. PR conflict, draft PR still open), re-run.
Do not transition to `completed` until exit 0.

### `relaunch` — terminal fail-state

1. Use the `Write` tool to create `sessions/<id>/pm-followup.md` keyed
   to findings (one bullet each: severity, suggested fix).
2. Run `tripwire session reopen <sid> --reason "<one-line summary>"
   [--reset-acks]`. This flips drafts back to draft, appends the PM
   follow-up stub to `plan.md`, optionally resets tripwire acks, and
   records the reopen audit entry. It also drives the
   `completed-to-paused-reopen` transition through `tripwire
   transition coding-session <sid> paused`.
3. Run `tripwire session spawn <sid> --resume`. This re-launches the
   agent and issues `tripwire transition coding-session <sid>
   executing`.

If `reopen` fails: read findings (e.g. PR closed, branch gone). For
squash-merged PRs, run `tripwire session normalise-branch <sid>`
first, then re-attempt.

Cross-link: `relaunch → coding-session.executing, kind: triggers`.
The resumed session reads `pm-followup.md` plus `plan.md`'s
`## PM follow-up` section, addresses each finding, pushes to the
existing PR pair, and posts a per-finding summary comment. When
`session complete` runs again, `pm-monitor` re-fires the trigger
and `code-review` runs from `received` — every iteration is
attributable.

## Review heuristics

When synthesising the multi-reviewer findings (self / superpowers /
codex), apply these decision rules:

- **Schema divergences from the spec** — `REQUEST_CHANGES` blocker, not
  `APPROVE_WITH_NOTES`. Do not defer schema fixes to downstream issues.
  The foundation that ships the schema must ship the canonical shape.
  See the verification-checklist's Schema parity section for the
  agent-side gate; if it's marked N/A but the diff contains a shipped
  schema, that's a `REQUEST_CHANGES` signal too.

## Requesting changes (in_review → executing)

If synthesis verdict is **relaunch** without going all the way through
the reopen path (e.g. you want changes before any merge):

1. Use the `Write` tool to create `pm-response.yaml` documenting the
   requested changes.
2. Run `tripwire transition coding-session <sid> executing`. This
   covers the `review-changes-requested` route.
3. Notify the executor (out of band) that changes are requested.

Runtime state (`claude_session_id`, `worktrees`) is preserved by the
transition.

## @codex trigger

PM comments `@codex` on the **project-pr** (not the tripwire-pr).
Codex listens on the code repo and surfaces findings as PR
comments. No structured contract — codex writes prose; PM extracts
to `codex.md`.

## Audit

Every station entry/exit appends to
`<project>/orchestration/monitor-log.yaml`. The synthesis verdict
is the load-bearing entry — it explains why the session merged or
relaunched.

## See also

- `SKILL.md` — PM entry point.
- `WORKFLOWS_NODE_RECONCILIATION.md` — sibling (C12).
- `templates/skills/verification/` — `gate-check` checklist.
- `MONITOR_CRITERIA.md` — `signal.session_pr_pair_open`.
- `superpowers-code-review.md` — subagent contract.
- `docs/WORKFLOW_ACTIONS.md` — every CLI command and `coding-session`
  transition.
