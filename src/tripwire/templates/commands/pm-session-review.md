---
name: pm-session-review
description: Structured session-PR review vs issue specs, with independent verification.
argument-hint: "<session-id> [--pr <number>]"
---

You are the project manager. Load the project-manager skill if not active.

$ARGUMENTS

The executor's claims are *evidence*, not *truth*. Verify them
independently. Don't trust `[x]` boxes — read the code that's
supposed to back them.

## Workflow

1. Parse `<session-id>` from the arguments.

2. **Scaffold the review record.** Run:
   ```bash
   tripwire session prepare-review <session-id>
   ```
   This writes `sessions/<id>/pr-review.yaml` populated with every member-issue
   AC and empty `verified_by` arrays. Your job is to fill the evidence in.

3. **Run the per-PR audit report (optional but recommended).** Run
   `tripwire session review <session-id> --format json --no-post-pr-comments`
   for the structured AC-vs-PR-diff comparison. Use its findings as
   evidence input for `pr-review.yaml`. If exit code 2, the CLI already
   identified blocking issues — confirm them.

4. **Per-issue verification.** For each issue in the session:
   - Open `issues/<key>/issue.yaml` and read the acceptance criteria.
   - Open the PR (`gh pr view <pr> --diff` for read-only;
     `gh pr checkout <pr>` if you need to run code or tests).
   - Walk every `[x]` in
     `sessions/<id>/artifacts/verification-checklist.md` mapped to
     this issue. For each, find the code or test that backs it.
     Soft-yeses (claim without evidence) get downgraded to `[ ]`
     in your notes.
   - **Fill `pr-review.yaml.issues[].acs[].verified_by`** with concrete
     `path/file.py:42` citations or short evidence strings. Placeholders
     like "manual verification needed" or empty arrays will fail the
     `pr_review/missing_evidence` gate.
   - Update `issues/<key>/verified.md` with the same evidence summary.

5. **Four-lens scrutiny on the PR overall.** Apply each lens
   independently — don't trust the executor's self-review:

   | Lens | What to check | Evidence |
   |------|---------------|----------|
   | AC met but not really | Soft-yeses surfaced in step 4 | Code diff vs claim |
   | Unilateral decisions | PR diff diverges from issue spec or session plan | List divergences with rationale or fix |
   | Skipped workflow | Commit history vs the executor's declared workflow (TDD red commits, validate runs, status messaging) | `git log --oneline` |
   | Quality degradation | Last commit vs first | Test density, naming, comment hygiene |

   Record each finding under `pr-review.yaml.four_lens.<lens>.findings`
   with `severity` (0–100), `decision`, and matching evidence
   (`fix_commit` for `fixed`, `follow_up: <KEY>` for `deferred`,
   `note` for `accepted`/`rejected`).

6. **External-reviewer comment** — *only if the project configures it*.
   Read `project.yaml.review.external_reviewer_mention`. If set
   (e.g. `"@codex"`), post the mention on the PR:
   ```bash
   gh pr comment <pr> --body "@codex please review"
   ```
   Then record the resulting comment URL under
   `pr-review.yaml.external_reviews.codex.comment_url`. The
   `pr_review/external_reviewer_missing` validator rule blocks
   transition until this is recorded. (Skip this step entirely if
   the project hasn't configured a mention.)

7. **Code-review skill** — *only if the project configures it*.
   Read `project.yaml.review.code_review_skill`. If set
   (e.g. `"superpowers:code-review:code-review"`), invoke that skill
   against the PR. Capture each finding it produces — at minimum
   `severity`, `category`, `location`, `text` — under
   `pr-review.yaml.external_reviews.code_review_skill.findings`,
   plus `invoked_at` (ISO timestamp). The
   `pr_review/code_review_skill_missing` rule blocks transition
   until invocation is recorded.

8. **Apply severity threshold.** For each finding (four-lens or
   code-review skill) at-or-above
   `project.yaml.review.severity_threshold` (default 65), the finding
   must have a `decision` of `fixed` (with `fix_commit`),
   `deferred` (with `follow_up`), or `rejected` (with `note`).
   Aggregate any unresolved high-severity findings into
   `pr-review.yaml.threshold_findings.unaddressed`. The
   `pr_review/threshold_findings_unaddressed` rule blocks transition
   if this list is non-empty.

9. **Independent validation gate.** From the project tracking repo
   (not the code repo):
   ```bash
   tripwire validate --format=summary
   ```
   This prints what `tripwire session transition` would catch — useful
   as a preview, but the real gate runs inside transition itself
   (v0.12: transition is atomic with validate).

10. **Decide and transition:**
    - All gates pass:
      ```bash
      tripwire session transition <session-id> verified
      ```
      The CLI runs validate atomically. If any `pr_review/*` rule fires,
      the transition is rolled back and you'll see exactly which gates
      failed — fix and retry.
    - Blocking findings: `gh pr review --request-changes` with the
      specific gaps; route back to the executor. Do not transition.

11. **Record the workflow prompt-check when approving.** If the review
    result allowed the session to enter `verified`, run:
    ```bash
    tripwire prompt-check invoke pm-session-review <session-id> --status verified
    ```

12. **Plan post-merge work.** If any concept nodes were touched, note
    them so you can do the §8 reconciliation in `WORKFLOWS_REVIEW.md`
    after merge.

13. **Report back:**
    - Overall verdict (matches `pr-review.yaml.verdict`)
    - Blocking findings + remediation
    - Suggested follow-up issues
    - Nodes to reconcile post-merge (if any)

## Red flags — common rationalizations

| Agent thought | Reality |
|---|---|
| "The verification-checklist has `[x]` for every item, ship it" | The `[x]` is the executor's claim. Verify it. |
| "The CLI returned exit 0, so it's fine" | The CLI checks structure. You check substance. |
| "I'll fix the small stuff post-merge" | Post-merge fixes pile up. Either fix in the PR or file a follow-up issue with a plan. |

## See also

- `WORKFLOWS_REVIEW.md` — full PR review procedure including §8
  post-merge node reconciliation
- `ANTI_PATTERNS.md` — common executor failure modes
