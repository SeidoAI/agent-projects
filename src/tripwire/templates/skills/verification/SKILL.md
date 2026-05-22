---
name: verification
description: >-
  Independent verification of a coding agent's PR. Rigorously checks
  that every acceptance criterion is met, detects reward hacking,
  catches missing tests, and writes the verified.md artifact. Runs as
  a read-only agent — cannot push code, only post PR reviews.
license: MIT
metadata:
  author: tripwire
  version: "1.0"
compatibility: >-
  Any target code repo. Requires `gh` CLI for PR operations. Uses
  the tripwire CLI for concept graph freshness checks.
---

# Verification

## When this skill loads

In v0.9.6 verification is not a free-standing agent. The checklist
below is consumed at four stations:

- **`code-review.gate-check`** — PM walks the checklist on the
  project-pr before dispatching reviewers (see
  `WORKFLOWS_CODE_REVIEW.md`).
- **`code-review.synthesis`** — PM compares the three independent
  reviews (self, superpowers subagent, codex) against the checklist
  for the `merge | relaunch` verdict.
- **superpowers code-review subagent** — applies the checklist
  read-only, writes `<project>/sessions/<id>/reviews/superpowers.yaml`.
- **`coding-session.executing` (deliver step)** — coding agent uses
  the same lens for its own `sessions/<id>/artifacts/self-review.md`.

The body is the checklist; framing depends on the station. The "no
push" rule below applies whenever a subagent or read-only PM loads
this skill. The coding agent's self-review is the only exception —
it's self-assessing work it already did, not policing someone else.

## You cannot push code

Agent definition is `github: read`. You can:

- Read the PR diff and comments.
- Run tests locally in a clone of the target repo.
- Run `tripwire` CLI commands on the project repo.
- Post PR reviews (approve / request-changes / comment).
- Write `verified.md` to the project repo, committed via your own PR.

If you want to "just fix this small thing", stop. Request changes —
the coding agent will be re-engaged.

## What you verify

1. **Missing acceptance criteria** — criteria in the issue body not
   met by the implementation.
2. **Reward hacking** — tests that pass without exercising the intent
   (mocks bypassing the real logic, hardcoded expected values,
   disabled assertions).
3. **Missing tests** — edge cases, error paths, security scenarios
   named in the issue but not covered.
4. **Security regressions** — auth bypass, missing authorization,
   tenancy leaks, hardcoded secrets.
5. **Scope creep** — changes beyond what the issue describes.
6. **Concept graph drift** — touched code a node points at without
   rehashing the node.

## Output contract

Two artifacts: (1) a PR review (`approve` or `request-changes`) with
specific evidence per finding; (2) `<project>/issues/<KEY>/verified.md`
committed via your own PR. Any failed check → request changes. Never
approve an incomplete implementation.

## Workflow

### Phase 1: Read the context

1. **Read the issue** at `<project>/issues/<KEY>/issue.yaml`. Note the
   acceptance criteria, the body, the required nodes.
2. **Read the PR**:
   ```bash
   gh pr view <number> --json title,body,headRefName,files,commits
   gh pr diff <number>
   ```
3. **Read the coding agent's session artifacts** in
   `<project>/sessions/<session-id>/artifacts/`:
   - `plan.md` — what they intended
   - `task-checklist.md` — what they did
   - `verification-checklist.md` — what they say they checked
   - `recommended-testing-plan.md` — what they suggest you test
   - `post-completion-comments.md` — their self-reported caveats

### Phase 2: Check acceptance criteria

4. **For each checkbox in `## Acceptance criteria`** in the issue body,
   confirm it's actually met by the PR diff. Not that a test
   claims to cover it — that the behaviour is implemented.
5. **Match the PR diff against the plan**. If the plan says X and
   the PR does Y, flag it.
6. **Run the tests locally**:
   ```bash
   gh pr checkout <number>
   make test
   ```
   If tests fail, that's an immediate `request-changes`.

### Phase 3: Detect reward hacking

7. **Read the new tests**. Red flags:
   - Tests that mock the entire function under test
   - Assertions like `assert True` or `assert result is not None`
     without checking actual values
   - Tests that wrap the entire body in a `try/except: pass`
   - Tests that were disabled (look for `@pytest.mark.skip`,
     `@unittest.skip`, commented-out tests)
   - Tests whose expected values are computed FROM the code under
     test (no real baseline)
8. **Check that the implementation does real work**. Red flags:
   - Stub functions that just return `None` or `"ok"`
   - Hardcoded responses where the issue expects computed logic
   - Error paths that catch everything and silently succeed

### Phase 4: Security review

9. **Authentication**: if the issue touches auth, confirm:
   - Input validation on every user-supplied field
   - Constant-time comparisons for secrets
   - Proper error envelopes (no stack traces or internal details)
   - Rate limiting where the issue requires it
10. **Authorization**: if the issue touches resources:
    - Every query scoped to the current tenant/user
    - No `superuser: true` shortcuts
    - `list` endpoints don't leak across tenants
11. **Secrets**: grep the diff for anything that looks like a key:
    ```bash
    gh pr diff <number> | grep -iE '(api_key|secret|token|password).*=.*["'\''][a-zA-Z0-9]{16,}'
    ```

### Phase 5: Concept graph consistency

12. **Identify nodes the PR touched**. For every source path in the
    diff, check if any node points at it (use
    `tripwire node refs reverse` or read the cache directly).
13. **Confirm nodes that point at changed code were rehashed**:
    ```bash
    tripwire node check
    ```
    If any active node is stale after the PR merges, flag it.
14. **Confirm new concept nodes were created** where the issue's
    Definition of Done says they should be.
15. **Run the project-level validator**:
    ```bash
    tripwire validate
    ```
    Any errors must be fixed before approval.

### Phase 6: Scope discipline

16. **Read the PR diff holistically**. Does it do anything beyond
    what the issue describes? Red flags:
    - Refactoring surrounding code unrelated to the issue
    - "Improvements" not requested in the issue
    - New dependencies not justified in `plan.md`
    - Changes to files the issue's `Repo scope` section doesn't mention

### Phase 7: Write the review

17. **All checks pass** — `gh pr review <number> --approve --body
    "..."`. Body has: result line ("Verification: PASS"), checked
    acceptance-criteria list, evidence (commands and one-line
    outputs).
18. **Any check fails** — `gh pr review <number> --request-changes
    --body "..."`. Body has: result line ("Verification: FAIL"),
    numbered findings (each with file:line evidence), numbered "what
    needs to change" instructions. Conclude with "I will re-verify
    after `tripwire validate` and push."

### Phase 8: Write `verified.md`

19. **Write `<project>/issues/<KEY>/verified.md`** using the
    template at `<project>/.claude/skills/project-manager/examples/`
    (adapt a completion-comment example — there's no dedicated
    `verified.md` template in v0).

    The doc should have:
    - **Result**: PASS or FAIL
    - **Evidence**: commands run, outputs (one-line summaries)
    - **Acceptance criteria table**: one row per criterion, status
    - **Findings** (for FAIL): specific issues with line references
    - **Follow-ups**: suggested new issues for out-of-scope findings

20. **Commit to the project repo** via your own PR (you have
    write access to the project repo, just not the target repo).
    Branch: `verifier/<KEY>-verified`.

21. **Run `tripwire validate`** on the project repo
    before pushing your commit. Your own changes must pass the gate.

## Operating rules

- **Read-only on target repos.** Never push commits. Never merge the
  PR. Never "just fix this small thing" — request changes.
- **Read tests, don't just run them.** A comprehensive-looking suite
  can be meaningless.
- **Run tests yourself.** CI may be cached; the agent may have edited
  tests between CI runs.
- **Check concept-graph freshness explicitly.** Validator catches
  dangling refs; freshness is a default-warning.
- **Be specific.** Name file and line per finding. Quote the
  acceptance criterion. Include the command output. Don't speculate
  without evidence.
- **Style nits aren't grounds for rejection** — they go in `fyi`
  messages or `post-completion-comments.md`. Scope creep IS — extra
  unauthorised work is its own problem even when the work is good.

## See also

- `references/REWARD_HACKING.md` — specific patterns to watch for
- `references/SECURITY_CHECKLIST.md` — auth and authz review items
- `.claude/skills/project-manager/references/SCHEMA_ISSUES.md` — the
  issue body structure
- `.claude/skills/project-manager/references/VALIDATION.md` — the
  validation gate
- `.claude/skills/agent-messaging/SKILL.md` — how to message the
  human if something is genuinely ambiguous
