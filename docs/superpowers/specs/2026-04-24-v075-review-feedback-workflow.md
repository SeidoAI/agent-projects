# Tripwire v0.7.5 — review-feedback workflow + spawn template tightening + structured PR-review artifact

**Status**: spec (ready for plan)
**Date**: 2026-04-24
**Depends on**: v0.7.4 (per-session project-tracking worktrees, validate-plan path-relativity, frontend copy retunes — `2026-04-24-v074-handoff.md`)
**Sibling**: v0.8 active concept graph (`2026-04-24-v08-bidirectional-concept-graph.md`) — independent track
**Source**: cross-cutting analysis of the parallel `frontend-views-core` + `frontend-views-detail` sessions (PRs #21, #22) on 2026-04-24. Patterns observable only because two sessions ran on the new v0.7.3 spawn template close in time.

---

## 1. Context

The first multi-session trial of the v0.7.3 spawn template (PR #21 + #22, parallel, ~30 min wall clock, $33.82 combined) produced exceptional self-reviews and clean exits — but cross-cutting analysis surfaced three patterns no single-PR review would catch:

1. **Stop-and-ask is silent on scope-creep during execution.** Both agents made unilateral expansions (TS interface widening, DTO additions, library version substitution, `<Toaster/>` mount). The trigger only fires on plan obsolescence, not "I need to expand scope to ship."
2. **Both agents skipped TDD with the same rationalization** ("spec was detailed enough that the red step was tautological"). Two independent agents reaching the same workaround = pattern, not lapse. The skill reference in CLAUDE.md is too easy to treat as optional.
3. **Both shipped 1 squash commit** because the exit protocol's "PR-open is your exit signal" implicitly encourages stage-then-PR with no incremental checkpoints. Result: unreviewable diffs at scale.

Plus two structural gaps:

4. **No formalized PM-review-then-feedback cycle.** Today the PM ad-hoc reviews PRs, posts comments, and… hopes the agent picks up the feedback somehow. There's no canonical "respawn for fixes" path.
5. **No structured PR-review artifact.** PM observations are buried in PR comments. Pattern detection across PRs requires re-reading every comment — doesn't compose into data.

v0.7.5 closes all five.

---

## 2. Items

### A. Spawn template additions (close the three trial-surfaced gaps)

**File:** `src/tripwire/templates/spawn/defaults.yaml`

#### A1. Mid-execution scope-creep disclosure

After the headless warning block, before the exit protocol, insert:

```
If during execution you make a change not described in the plan
(new dependency, new DTO field, interface widening, library version
substitution, mounting a globally-scoped UI element, etc.), append
it to `decisions.md` in the project-tracking worktree before
continuing. One paragraph per decision: what you did, what the plan
said vs reality, why your choice was the minimum scope to meet the
stated AC. Do NOT treat scope expansions as implicit — name them.
This file is part of your PR; the PM reviews it alongside the
diff.
```

This converts silent unilateral decisions into a structured, reviewable trail. The agent's existing self-review behavior already documents these — making it a separate artifact (a) surfaces them earlier (PR-open time, not post-PR), and (b) makes them grep-able for cross-PR pattern detection.

#### A2. Explicit TDD mandate

After A1, before the exit protocol, insert:

```
Test-Driven Development is required for every component you write
that has observable behaviour. Sequence per component:
  1. Write a failing test that asserts the AC.
  2. Commit the red test with message `test: <component> red`.
  3. Implement the component until the test passes.
  4. Commit the implementation with message
     `feat(<key>): <component>`.
The `superpowers:test-driven-development` skill defines edge cases.
"The spec was detailed enough that the red step was tautological"
is not a valid skip — write the test anyway. Two parallel sessions
in v0.7.3 used that exact rationalization; we caught it. Don't
repeat it.
```

Naming the prior failure mode in the prompt itself is a deliberate anti-rationalization tactic.

#### A3. Per-step commit checkpoints

Modify the existing exit protocol block (currently begins with "Exit protocol — how you signal you're done"). Before the existing "PR-open is your exit signal" paragraph, insert:

```
Commit cadence during execution:
- After each numbered plan step, commit your changes with message
  `step-N(<key>): <step title>` before moving to the next step.
- This breaks the single-squash anti-pattern that makes large PRs
  unreviewable. The PM gets natural rollback points. Squash on
  merge is the PR's job, not yours.
```

This doesn't change the exit signal; it changes the commit graph leading to it.

---

### B. Review-feedback cycle as default workflow

#### B1. Update `resume_prompt_template` in defaults.yaml

Today's template assumes the PM updated `plan.md` with a `## PM follow-up` section. With B baked in, also point the agent at PR comments (the PM may have written feedback there too):

```yaml
resume_prompt_template: |
  Resuming session {session_id}.

  The PM has provided feedback. Two places to look:
  1. PR comments on your PR — read every PM comment posted since
     your last commit. Each PM comment may include specific bug
     findings with suggested fixes; address each one explicitly.
  2. The plan at {plan_path} — re-read any `## PM follow-up`
     section the PM may have added.

  Your previous conversation is preserved — you have the full
  context of what you've already tried. Continue from where you
  stopped, addressing the PM's feedback in priority order
  (criticals first, then real bugs, then nice-to-fix).

  Exit protocol unchanged: when fixes land, push + the PR auto-
  updates. Post a short follow-up comment on the PR summarising
  what you changed in response to each PM finding. If you disagree
  with a finding, write your reasoning in the follow-up comment
  rather than silently ignoring it.
```

#### B2. Add `tripwire session reopen <session-id>` command

Today, completed sessions can't be re-spawned because the status guard rejects `completed` → `executing`. Two options: (a) loosen the guard, (b) add a `reopen` command that explicitly transitions `completed` → `executing` (with `--reason` capture for audit).

**Recommend (b).** Keeps the lifecycle state machine explicit; gives the PM a deliberate "I am reopening this for fixes" action. Implementation:

```python
@session_cmd.command("reopen")
@click.argument("session_id")
@click.option("--reason", required=True, help="Why are you reopening?")
@click.option("--project-dir", ...)
def session_reopen_cmd(session_id, reason, project_dir):
    """Move a completed session back to executing for PR-fix iteration.

    Records the reopening in `~/.tripwire/logs/<project>/audit.jsonl`
    and adds a `## PM follow-up` section to the session's plan.md
    pointing at the PR. The agent should be re-spawned with
    `tripwire session spawn <id> --resume` immediately after.
    """
```

Then the PM's loop is:

```
tripwire session reopen <id> --reason "PR review feedback"
tripwire session spawn <id> --resume
```

#### B3. Codify the cycle in `WORKFLOWS_REVIEW.md`

Add a new top-level section "Review feedback cycle" describing the canonical loop:

```
1. Agent ships PR. Process exits cleanly per the new exit protocol.
2. PM reviews:
   a. Read the agent's self-review (the four-lens block from the
      spawn template).
   b. Walk the verification-checklist independently.
   c. Run `tripwire validate --strict` against the project repo.
   d. Optionally dispatch sub-agents for independent bug scans
      and a cross-cutting pattern analysis (see §"Pattern detection"
      below).
3. PM writes the structured PR-review artifact (see Item C).
4. PM posts findings on the PR — one comment per concern, each
   with a suggested fix. Mark severity (critical / real bug / nice
   to fix). The artifact is the PM's view; the PR comments are the
   agent's actionable list.
5. PM:
   a. Either approves and merges (no findings), OR
   b. `tripwire session reopen <id> --reason "..."` then
      `tripwire session spawn <id> --resume`.
6. Agent (resumed) reads PR comments + plan.md `## PM follow-up`
   section. Addresses each finding. Pushes. Posts a follow-up
   comment summarising what they changed per finding.
7. Loop 2-6 until verdict is approve+merge.
8. `tripwire session complete <id>`. Status → completed.
```

This is the new default. Document in CLAUDE.md too so PM agents new to the project see it.

---

### C. Structured PR-review artifact (`pm-review.md`)

#### C1. Where it lives

`sessions/<session-id>/artifacts/pm-review.md`. Lives alongside the agent's self-review (in the PR), but in the project-tracking repo as a structured per-iteration record.

If the session goes through multiple review cycles (PR-fix iteration), each cycle appends a new top-level section to the same file: `## Review iteration 1 (2026-04-24)`, `## Review iteration 2 (2026-04-25)`, etc. Each iteration is self-contained — frontmatter snapshot per iteration would inflate the file; instead, the **frontmatter stays at the top and reflects the LATEST iteration's verdict**, with the body carrying the historical record.

#### C2. Schema (frontmatter + body)

```yaml
---
session_id: frontend-views-core
pr_number: 21
reviewed_at: 2026-04-24T18:30:00Z
reviewer: pm-agent
iteration: 2
verdict: request_changes      # approved | request_changes | needs_rework | abandoned
recommended_next: respawn_for_fixes  # merge | respawn_for_fixes | abandon
# Per-lens findings count
lens_findings:
  ac_met_but_not_really: 4
  unilateral_decisions: 5
  skipped_workflow: 3
  quality_degradation: 0
# Independent bug scan
bug_findings_critical: 0
bug_findings_real: 2
bug_findings_minor: 2
# Behavioural signals — yes / partial / no
template_adherence:
  reconnaissance_pass: yes
  stop_and_ask_threshold: not_triggered
  four_lens_self_review: yes
  scope_creep_disclosure: no       # missing in v0.7.3; present from v0.7.5
  tdd_followed: no                 # both v0.7.3 sessions skipped
  per_step_commits: no             # both v0.7.3 sessions used 1 squash commit
  exit_on_pr_open: yes
# Cross-PR pattern markers (filled when relevant patterns observed)
cross_pr_patterns:
  - "TDD skipped with rationale 'spec was detailed enough'"
  - "1-squash-commit pattern across both parallel sessions"
  - "Unilateral DTO/interface widening to ship feature"
---

## Review iteration 1 (2026-04-24T18:30:00Z) — verdict: request_changes

### Critical
1. ...

### Real bugs
1. ...

### Nice to fix
1. ...

### Cross-PR patterns
- ...

### Recommended next
respawn_for_fixes — see PR comments for the actionable list.
```

#### C3. Why structured

- **Cross-iteration history.** Each review cycle appends; the file becomes the audit log of "how many round trips this session took, what got caught at which iteration."
- **Cross-session pattern detection.** `tripwire pm-review patterns` (future CLI) can grep all `pm-review.md` files for fields like `tdd_followed=no` and surface aggregates. Without structure, you'd be diffing prose.
- **Template-iteration feedback loop.** The `template_adherence` block tells us, over time, which prompt-template instructions are landing and which are getting skipped. Direct input to v0.8/v0.9 template tuning.
- **Verdict trend.** A session that takes 4 iterations to merge is a different beast from one that takes 1 — the artifact captures it.

#### C4. Manifest update

Add `pm-review` to `src/tripwire/templates/artifacts/manifest.yaml`:

```yaml
- name: pm-review
  file: pm-review.md
  template: pm-review.md.j2
  produced_at: in_review
  produced_by: pm
  owned_by: pm
  required: true
  approval_gate: false
```

`produced_at: in_review` — written when the session is in PM-review state. Add a corresponding template at `src/tripwire/templates/artifacts/pm-review.md.j2` rendering the frontmatter scaffold so `tripwire session scaffold --artifact pm-review.md` works.

#### C5. CLI helper (optional, polish)

`tripwire pm-review init <session-id>` — scaffold the next iteration block in an existing `pm-review.md`, pre-filling `iteration: <N+1>` and a stub frontmatter. Not strictly needed for v0.7.5 — PM can write the file directly per the schema. Worth filing as a v0.7.6 polish if usage shows it'd help.

---

### D. Pattern-detection guidance in `WORKFLOWS_REVIEW.md`

Add a new section "Pattern detection across PRs":

```
PM review covers more than per-PR critique. When multiple sessions
have shipped close in time (same week, same template version),
examine PRs together for patterns. Patterns reveal template gaps
that single-PR critique can't see — by definition they're shared
behaviours, not individual lapses.

Patterns to scan for:

| Category | What to look for | Where to record |
|---|---|---|
| Workflow adherence | TDD skipped? Single-squash-commit? Skill never read? | `pm-review.md` `template_adherence` block |
| Decision discipline | Unilateral scope-expansion themes (which kinds of choices recur?) | `cross_pr_patterns` list |
| Common failure modes | State isolation bugs (cache keys, tab state, pagination)? Async ordering? | bug_findings + cross_pr_patterns |
| Plan-vs-reality | Reconnaissance findings — what kind of obsolescence keeps recurring? | `cross_pr_patterns` |

If a pattern recurs across 2+ sessions, file it as a v0.X.Y template
addition (or a v0.8 spec item) — don't expect agent self-discipline
to fix it. Templates are leverage; reminders aren't.

Use sub-agents (Explore, code-review, general-purpose) for the
independent bug scan and cross-cutting pattern pass. Reading every
diff yourself doesn't scale; sub-agents see what you'd miss when
fatigued.
```

Also: update `WORKFLOWS_REVIEW.md`'s existing red-flags table with two new rows:

```
| Agent thought | Reality |
| "I'll just review this PR in isolation, the patterns are obvious" | If 2+ sessions completed close in time, scan together. Single-PR review misses the discipline patterns that span sessions. |
| "The PR comment captures everything, I don't need pm-review.md" | The PR comment is for the dev agent. pm-review.md is for the data layer that surfaces template-iteration patterns over time. Both are needed. |
```

---

## 3. Out of scope (deliberately)

- **Auto-classification of cross-PR patterns** (LLM groups findings into themes automatically). v0.7.5 ships the artifact + manual inspection. Auto-grouping is a v0.8 nice-to-have once we have data to train against.
- **PR-review dashboard UI.** The frontend can render `pm-review.md` files later; v0.7.5 ships the data only.
- **Patterns-CLI** (`tripwire pm-review patterns --since 30d`). Same — v0.7.6/v0.8 once enough artifacts exist to query meaningfully.
- **Rolling back v0.7.4 features.** v0.7.5 is purely additive.

---

## 4. Implementation order

1. **B1 (`resume_prompt_template` update)** — tiny, ships the cycle's runtime piece. Land first so the trial can use it.
2. **A (spawn template additions: scope-creep disclosure, TDD mandate, per-step commits)** — three blocks added to the same file. Ship next; immediately benefits future sessions.
3. **B2 (`tripwire session reopen` command)** — small CLI addition. Ships once A and B1 are in.
4. **B3 (`WORKFLOWS_REVIEW.md` cycle docs)** — pure docs. Land alongside #3.
5. **C (structured `pm-review.md` artifact)** — new manifest entry, new j2 template, schema-backed model if helpful. Mid-size; can land independently of A/B.
6. **D (`WORKFLOWS_REVIEW.md` pattern-detection section)** — pure docs. Last because it cross-refs the C artifact's schema.

Items can land in two PRs:
- `feat(v0.7.5): spawn template tightening + resume cycle` → A + B1 + B2 + B3
- `feat(v0.7.5): pm-review.md structured artifact + pattern detection` → C + D

Or one larger PR if convenient.

---

## 5. Critical files

| Path | Touch |
|---|---|
| `src/tripwire/templates/spawn/defaults.yaml` | Insert A1 + A2 + A3 blocks; update resume_prompt_template (B1) |
| `src/tripwire/cli/session.py` | New `session_reopen_cmd` (B2) |
| `src/tripwire/cli/main.py` | Register the reopen command if it ends up as a top-level (likely not — keep under `session`) |
| `src/tripwire/templates/skills/project-manager/references/WORKFLOWS_REVIEW.md` | Add "Review feedback cycle" section (B3) + "Pattern detection across PRs" section (D) |
| `src/tripwire/templates/artifacts/manifest.yaml` | Add `pm-review` entry (C4) |
| `src/tripwire/templates/artifacts/pm-review.md.j2` | NEW (C2 schema) |
| `src/tripwire/models/session.py` (or new `pm_review.py`) | Optional Pydantic model for pm-review frontmatter (C2) |
| `tests/unit/test_session_reopen_cli.py` | NEW |
| `tests/unit/test_pm_review_scaffold.py` | NEW |

---

## 6. Verification

End-to-end after all items land:

1. **Resume template includes both PR comments + plan.md hooks.** Spawn → complete → reopen → spawn --resume; the rendered kickoff at `<worktree>/.tripwire/kickoff.md` references "PR comments" AND "PM follow-up section in plan.md". ✓ if both phrases present.
2. **Scope-creep disclosure required.** Run a session whose work necessarily expands scope (add a dep, widen an interface). Confirm the agent writes `decisions.md` in the project-tracking worktree before opening the PR. (Soft check; agent may deviate, but the prompt should have asked.)
3. **TDD mandate enforced.** Run a session and inspect the commit graph: should see `test: <component> red` commits BEFORE `feat: <component>` commits. If a single squash is observed, A2 didn't land.
4. **Per-step commits.** Same session — commit count ≥ N where N = number of plan steps. (Approximate; squash on merge collapses these for the merged history but the branch tip should have them.)
5. **`tripwire session reopen` works.** Complete a session, run `tripwire session reopen <id> --reason "..."`, verify status → executing, verify audit log entry written, verify spawn --resume succeeds.
6. **`pm-review.md` scaffold.** `tripwire session scaffold <id> --artifact pm-review.md` renders the frontmatter scaffold. Validator's `artifact/missing` check fires if a session reaches `verified` without one (since `produced_at: in_review`, `required: true`).
7. **Cross-PR pattern detection workflow.** Run two parallel sessions on v0.7.5+, complete both, write pm-review.md for each. Manual scan should surface common `template_adherence` values; the cross_pr_patterns list captures recurring themes.
8. **Full suite.** `uv run python -m pytest tests/ -q` — ≥1610 + new tests passing.
9. **Lint.** `uv run ruff check` and `uv run ruff format --check` clean.

---

## 7. Open questions for the project agent

- **`decisions.md` location.** I specified "project-tracking worktree" — but maybe it should live at `sessions/<id>/artifacts/decisions.md` for consistency with other artifacts? Sub-question: should it be a manifest entry too (like pm-review.md), or stay as agent-owned ad-hoc?
- **Iteration counting on `pm-review.md`.** The frontmatter holds the LATEST iteration's verdict. Is that the right shape, or do we want a list of iteration objects in frontmatter (with body carrying narrative per iteration)? The latter is more structured but heavier to author.
- **Reopen + resume vs. one command.** Is `tripwire session reopen` always followed by `tripwire session spawn --resume`? If yes, fold them: `tripwire session reopen <id> --reason "..." --spawn`. If no (PM might want to update plan first, then spawn manually), keep them separate. **Recommend: keep separate.** PM needs the gap to write the `## PM follow-up` section first.
- **Should the `## PM follow-up` plan section be auto-generated** by `tripwire session reopen` (e.g. with a placeholder pointer to PR URL)? Probably yes — closes the "PM forgot to update plan" failure mode. One-liner: append a stub section if not present.

---

## 8. Why this matters

The v0.7.3 spawn template is a clear inflection — the four-lens self-review template alone has dramatically improved review quality. The v0.7.5 changes are about turning **observation → intervention**:

- Today: PM sees a pattern across PRs, files a mental note, hopes to remember next time.
- v0.7.5: pattern lands in a structured artifact; recurring patterns trigger template additions; the loop closes.

Every template tightening up to now has been reactive — wait for an agent to fail in a new way, then fix the prompt. v0.7.5 makes that loop explicit and grep-able. Three iterations from now, the project agent should be able to ask: "what fraction of sessions in the last 30 days skipped TDD?" and get an actual number from `pm-review.md` files. Without C, that question never gets answered; with C, it's a one-liner.
