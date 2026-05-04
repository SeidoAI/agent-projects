# Workflow: Code Review

Closes a coding session. The session produces a **PR pair** —
`tripwire-pr` (project tracking repo) and `project-pr` (code repo).
Both must land atomically; either alone leaves the project graph
and shipped code out of sync. v0.9 splits this cycle out of
`coding-session` so each station has its own controls and audit.

## Trigger

`pm-monitor` fires `signal.session_pr_pair_open` when both PR URLs
are set on `session.yaml` and both PRs are in
`{open, ready_for_review}`. Dispatch routes to
`code-review.received`. See `MONITOR_CRITERIA.md`.

## Stations

### `received`
Confirm the PR pair is present and live. Tripwires
`v_pr_pair_present`, `v_branch_alive`. Records PR URLs, branches,
head SHAs — pinning means downstream stations measure against the
commit the review started from.

### `gate-check`
1. `gh pr checkout <project-pr>`.
2. `tripwire validate` against the tripwire-pr branch.
3. Walk the verification checklist
   (`templates/skills/verification/`).
4. `tripwire session review <id> --write-verified` → emits
   `docs/issues/<KEY>/verified.md` per closed issue.

`--write-verified` runs here because once branches merge or delete,
the per-issue evidence (diff ranges, test outputs, AC walk) cannot
be reconstructed. Tripwires `v_validate_passes_on_branch`,
`v_verified_md_written` — failing either halts before reviewers
are dispatched.

### `independent-reviews`
Three parallel reads:

1. **Self-review.** PM reads the agent's four-lens self-review on
   the project-pr.
2. **Superpowers subagent.** PM dispatches a `superpowers
   code-review` subagent per `superpowers-code-review.md`. Output:
   `<project>/sessions/<id>/reviews/superpowers.yaml`. Implementation
   lives outside this repo; tripwire only consumes the file.
3. **Codex.** PM comments `@codex` on the **project-pr** (codex
   listens on the code repo). Findings surface as PR comments; PM
   extracts to `<project>/sessions/<id>/reviews/codex.md`.

If a reviewer doesn't return (subagent timeout, codex no-reply
within window), the PM proceeds and records the absence in
synthesis.

### `synthesis`
PM reads all three reviews end-to-end and writes
`<project>/sessions/<id>/reviews/synthesis.md`: one row per finding
(severity, source, PM verdict accept / reject / defer), final
overall verdict (`merge` | `relaunch`).

Decision rule of thumb:

- Any **blocking** finding not rejected with written rationale →
  relaunch.
- Any **major** finding outside `session.repo_paths` → relaunch.
- Self + superpowers clean, codex only nits → merge.
- Reviewers disagree on a major finding → PM is tiebreaker;
  rationale recorded in synthesis.

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
Identify which concept nodes the project-pr touches (via the
agent's divergence callouts and `verified.md` files). For each:

1. Node body diverges from shipped behaviour → update the body
   (default: shipped behaviour wins; see `WORKFLOWS_REVIEW.md`
   step 8).
2. Concept appears in implementation with no node → create it.
3. Underlying source file changed → rehash `source.content_hash`.

Cross-link: `node-reconcile → concept-freshness.detected,
kind: triggers`. Reconciling before merge keeps the responsibility
scoped to the session that caused the drift instead of leaking it
as project-wide drift afterward.

### `merge` — terminal pass-state
1. `gh pr merge <tripwire-pr> --merge`.
2. `gh pr merge <project-pr> --merge`.
3. Emit `merge` event.

Tripwires `v_no_stale_nodes_post_reconcile` (guards "PM said merge
but freshness scan still has open items"),
`v_done_implies_issue_artifacts_on_main` (guards "session done but
verified.md / comments / closing comment never landed on main").

### `relaunch` — terminal fail-state
1. Write `sessions/<id>/pm-followup.md` keyed to findings (one
   bullet each: severity, suggested fix).
2. `tripwire session reopen <id> --reason "<one-line summary>"`.
3. `tripwire session spawn <id> --resume`.

Cross-link: `relaunch → coding-session.executing, kind: triggers`.
The resumed session reads `pm-followup.md` plus `plan.md`'s
`## PM follow-up` section, addresses each finding, pushes to the
existing PR pair, and posts a per-finding summary comment. When
`session complete` runs again, `pm-monitor` re-fires the trigger
and `code-review` runs from `received` — every iteration is
attributable.

## @codex trigger

PM comments `@codex` on the **project-pr** (not the tripwire-pr).
Codex listens on the code repo and surfaces findings as PR
comments. No structured contract — codex writes prose; PM extracts
to `codex.md`.

## Audit trail

Every station entry/exit appends to
`<project>/orchestration/monitor-log.yaml`. The synthesis verdict
is the load-bearing entry — it tells the next reader why the
session merged or relaunched.

## See also

- `SKILL.md` — PM agent entry point.
- `WORKFLOWS_NODE_RECONCILIATION.md` — dedicated reconciliation
  workflow (lands in C12).
- `templates/skills/verification/` — the checklist `gate-check`
  walks.
- `MONITOR_CRITERIA.md` — `signal.session_pr_pair_open`.
- `superpowers-code-review.md` — external subagent contract.
- `WORKFLOWS_REVIEW.md` — legacy single-route review doc; C12
  splits it.
