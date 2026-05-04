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

2. Run `tripwire session review <session-id> --format json --no-post-pr-comments`.
   Parse the JSON. If exit code 2, the CLI already identified
   blocking issues — confirm them and stop here.

3. **Per-issue verification.** For each issue in the session:
   - Open `issues/<key>/issue.yaml` and read the acceptance criteria.
   - Open the PR (`gh pr view <pr> --diff` for read-only;
     `gh pr checkout <pr>` if you need to run code or tests).
   - Walk every `[x]` in
     `sessions/<id>/artifacts/verification-checklist.md` mapped to
     this issue. For each, find the code or test that backs it.
     Soft-yeses (claim without evidence) get downgraded to `[ ]`
     in your notes.
   - Update `issues/<key>/verified.md` with specific evidence:
     `path/file.py:42`, test name, or "manual smoke passed +
     screenshot." No vague "looks good."

4. **Four-lens scrutiny on the PR overall.** Apply each lens
   independently — don't trust the executor's self-review:

   | Lens | What to check | Evidence |
   |------|---------------|----------|
   | AC met but not really | Soft-yeses surfaced in step 3 | Code diff vs claim |
   | Unilateral decisions | PR diff diverges from issue spec or session plan | List divergences with rationale or fix |
   | Skipped workflow | Commit history vs the executor's declared workflow (TDD red commits, validate runs, status messaging) | `git log --oneline` |
   | Quality degradation | Last commit vs first | Test density, naming, comment hygiene |

   Capture findings in your draft PR review body — one short note
   per lens.

5. **Independent validation gate.** From the project tracking repo
   (not the code repo):
   ```bash
   tripwire validate --strict
   ```
   Don't trust the executor's claim that this passed — run it
   yourself. If it fails, the PR fails review.

6. **Decide:**
   - All AC verified, no unresolved lens findings, validate clean
     → approve (and merge if `auto_merge_on_pass`).
   - Anything unverified or any blocking finding → `gh pr review
     --request-changes` with the specific gaps; route back to the
     executor.

7. **Post the review:**
   - `tripwire session review <session-id> --post-pr-comments` for
     the per-issue verification summary, OR
   - `gh pr review <pr> --approve|--request-changes --body "..."`
     with your richer four-lens body.

8. **Plan post-merge work.** If any concept nodes were touched, note
   them so you can do the §8 reconciliation in `WORKFLOWS_REVIEW.md`
   after merge.

9. **Report back:**
   - Overall verdict
   - Blocking findings
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
