---
name: pm-session-review
description: Structured review of a session's PR against issue specs.
argument-hint: "<session-id> [--pr <number>]"
---

You are the project manager. Load the project-manager skill if not active.

$ARGUMENTS

Workflow:

1. Parse `<session-id>` from the arguments.
2. Run `tripwire session review <session-id> --format json --no-post-pr-comments`.
3. Parse the JSON report.
4. For each issue in the session, do a manual pass:
   - Open `issues/<key>/issue.yaml` and read acceptance criteria.
   - Open the PR diff (`gh pr view <pr> --diff`) and evaluate each criterion
     against the actual code.
   - Update `issues/<key>/verified.md` with specific evidence (file:line, test
     name, or "manual smoke passed") for each criterion.
5. If any unverified criteria remain, set the verdict to `rejected`.
6. If the CLI already returned exit 2, confirm and stop; the PR is blocking
   until addressed.
7. Post a PR comment summarising the review: run
   `tripwire session review <session-id> --post-pr-comments` (or do it via
   `gh pr comment` directly with a richer body you've assembled).
8. Report back with:
   - Overall verdict
   - Any blocking findings that must be fixed
   - Suggested follow-up issues
