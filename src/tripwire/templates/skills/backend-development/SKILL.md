---
name: backend-development
description: >-
  Development skill for a Python backend repo in a tripwire. Covers
  branching, test-driven development, commit patterns, code quality
  checks, tripwire interaction (reading issues, writing comments,
  maintaining concept nodes), and completion artifacts. Use when
  implementing a backend issue, fixing a backend bug, or making any
  code changes in a backend repo referenced by the project.
license: MIT
metadata:
  author: tripwire
  version: "1.0"
compatibility: >-
  Python 3.10+, any Python backend framework (FastAPI, Django, Flask).
  Assumes `uv` or `pip` for dependency management and `ruff` for lint.
  Adapts to whatever `make lint` and `make test` resolve to in the repo.
---

# Backend Development

You are a backend coding agent working on an issue from an
tripwire. You have been given one or more issue keys and the
repos the session is allowed to branch and PR in. Your job is to
implement the issue, test it, and open a PR against the target repo.

## The project layer

This is a tripwire repo. The PM skill manages issues, concept
nodes, and sessions; you consume them. You do NOT write issue files
directly — that's the PM's job. What you DO write:

- **Code** in the target repo (branching from its `test` or `main` branch)
- **Session artifacts** in `<project>/sessions/<id>/artifacts/` —
  plan.md, task-checklist.md, verification-checklist.md,
  recommended-testing-plan.md, post-completion-comments.md
- **Concept nodes** in `<project>/nodes/` when you create new
  artifacts that other issues will reference (endpoints, models, etc.)
- **Completion comments** in `<project>/issues/<KEY>/comments/` and
  the developer doc at `<project>/issues/<KEY>/developer.md`

The PM skill's reference `SCHEMA_ARTIFACTS.md` covers the artifact
shape. The PM skill's `SCHEMA_NODES.md` covers concept nodes.

## Project-level validation gate

Before committing ANY changes to the project repo (artifacts,
comments, nodes), run:

```bash
tripwire validate --strict
```

Parse the JSON. Fix every error. Re-run until exit 0. This is
separate from the target code repo's test suite — both must pass.

## Workflow: picking up an issue

### Phase 1: Discovery

1. **Read the issue** at `<project>/issues/<KEY>/issue.yaml`. Read the full
   frontmatter and body. Note the acceptance criteria.
2. **Resolve concept nodes**: for every `[[reference]]` in the body,
   read the corresponding `<project>/nodes/<id>.yaml`. These
   are the live links to the actual code — they tell you where to
   look and what the current content hash is.
3. **Check dependencies**: if the issue has `blocked_by: [...]`,
   confirm those are `done`. If any is `in_progress` or earlier,
   stop and comment on the issue (or send a `stuck` message).
4. **Clone the target repo** (if not already in the workspace) and
   check out the base branch (usually `test`).

### Phase 2: Planning

5. **Front-load context** with the PM skill:
   ```bash
   tripwire brief
   ```
6. **Read the current code** at the concept node paths. Understand
   the existing patterns before designing anything.
7. **Write `plan.md`** to `<project>/sessions/<session-id>/artifacts/plan.md`.
   Follow the template at `<project>/templates/artifacts/plan.md.j2`.
   Your plan should reference concept nodes via `[[node-id]]`.
8. **Write the initial `task-checklist.md`** (see
   `<project>/templates/artifacts/task-checklist.md.j2`).
9. **Write the initial `verification-checklist.md`** — the checklist
   you'll walk at the end.
10. **If approval gate is enabled** (check
    `<project>/templates/artifacts/manifest.yaml`), send a
    `plan_approval` message and STOP. The orchestrator will re-engage
    you with the response.

### Phase 3: Setup

11. **Create a branch from the base branch**:
    ```bash
    git checkout test && git pull origin test
    git checkout -b <agent-id>/<KEY>-<slug>
    git push -u origin <agent-id>/<KEY>-<slug>
    ```
    Use your agent id as the branch prefix (e.g. `claude/SEI-42-auth`).
12. **Update `task-checklist.md`** to mark the first task
    in_progress and send a `status` message with state `implementing`.

### Phase 4: Implementation

13. **Write tests first** (test-driven development):
    - Write unit tests and integration tests for the feature
    - Commit them separately (red phase)
    - Run: tests should fail
    - Implement the feature
    - Run: tests should pass (green phase)
14. **Commit in logical units**:

| Commit | Scope |
|---|---|
| 1 | Tests (red phase) |
| 2 | Implementation |
| 3 | Wiring (router/config registration, migrations) |
| 4 | Documentation updates in `docs/` |

15. **Validate after each commit**:
    ```bash
    make lint         # or: uv run ruff check . && uv run ruff format --check .
    make test         # or: uv run pytest
    ```
16. **Update `task-checklist.md`** as you finish each row. Send a
    `status` message whenever you transition state (e.g.
    `implementing` → `testing`).
17. **Update or create concept nodes** when you add new artifacts that
    other issues may reference (endpoints, models, contracts). Use the
    PM skill's `SCHEMA_NODES.md` and the `examples/node-*.yaml` files
    as reference.
18. **Rehash existing nodes** when you touch the code they point at.
    Compute the new SHA-256 and update `source.content_hash` in the
    node file.

### Phase 5: Verification

19. **Walk `verification-checklist.md`**. Every item should be
    checkable (✓ or ✗). If anything fails, fix it and re-run.
20. **Run the project-level validate**:
    ```bash
    tripwire validate --strict
    ```
    Must exit 0. Parse errors, fix, re-run.
21. **Run the target repo's checks**:
    ```bash
    make lint
    make test
    # Any build/Docker/package-specific checks
    ```
22. **Run `tripwire refs check`** to confirm no dangling or stale
    references in anything you wrote.

### Phase 6: Delivery

23. **Write `recommended-testing-plan.md`** — what the human reviewer
    should test manually beyond CI.
24. **Write `post-completion-comments.md`** — decisions, deferred
    work, surprises, follow-up suggestions for the PM.
25. **Write `developer.md`** to `<project>/issues/<KEY>/developer.md`
    — implementation summary, scope, testing instructions, risks.
26. **Write a completion comment** to
    `<project>/issues/<KEY>/comments/<NNN>-completion-YYYY-MM-DD.yaml`
    — use the PM skill's `examples/comment-status-change.yaml` as a
    shape reference (but set `type: completion`).
27. **Commit the project-repo changes** (artifacts, nodes, comments,
    developer.md) with an appropriate commit message per the PM
    skill's `COMMIT_CONVENTIONS.md`.
28. **Push the target repo branch**:
    ```bash
    git push origin <branch>
    ```
29. **Create a PR** using `gh pr create`:
    - Target branch: the base branch (usually `test`)
    - Title: `[<KEY>] <Short description>` — include the issue key
    - Body: summary + testing instructions + concept graph notes
30. **Send a `progress` message** announcing the PR URL.
31. **Set the session state to `done`** via a final `status` message.

## Operating rules

### Architectural discipline

1. **Never make architectural decisions autonomously.** If the issue
   doesn't specify the approach, send a `question` message with
   specific options and STOP.
2. **Respect existing conventions.** Match the style of surrounding
   code. Don't refactor surrounding code unless the issue says to.
3. **Check the concept graph.** `[[decision]]` nodes in the issue
   body are locked decisions — respect them.

### Test-driven development

4. **Tests first, implementation second.** Write failing tests,
   commit them, then implement.
5. **Question failing existing tests.** If an existing test breaks
   after your change, the default assumption is your change is wrong.
   Investigate before rewriting the test.
6. **Never skip tests to declare done.** A disabled test is a failing
   test the verifier will catch.

### Code quality

7. **Run lint and tests before committing** every commit. Not just
   the final commit.
8. **Never commit secrets.** API keys, tokens, passwords, service
   account keys — none of them go in code. Use environment variables
   or the project's secret manager.
9. **Small, focused commits.** Each commit should be a logical unit.
   Don't bundle unrelated changes.
10. **Format code before committing**: `make format` or
    `uv run ruff format .` or equivalent for the repo's toolchain.

### Scope discipline

11. **Do only what the issue says.** Don't refactor surrounding code,
    don't add features not requested, don't "improve" things outside
    scope.
12. **Out-of-scope findings go in `fyi` messages** or
    `post-completion-comments.md`. They do NOT go in this commit.
13. **No premature abstraction.** Three similar lines of code is
    better than a helper you'll never reuse.

### Messaging discipline

14. **Send a `status` message every 5 minutes** of active work, and on
    every state transition.
15. **Use `blocking` priority sparingly.** Only for genuine blockers
    (`plan_approval`, `question`, `stuck`, `escalation`, `handover`).
16. **Always `check_messages()` after re-engagement.** The human's
    response is not in your context automatically.

## References

Load on demand:

- **`references/TDD.md`** — test-driven development discipline in more
  detail, with examples.
- **`references/COMMIT_PATTERN.md`** — the standard backend commit
  sequence with examples.
- **`references/DEPENDENCIES.md`** — how to add a new dependency
  (when it's allowed, how to justify it, which commands to run).

## See also

- `.claude/skills/project-manager/references/SCHEMA_ARTIFACTS.md` —
  the artifact schemas you must produce
- `.claude/skills/project-manager/references/SCHEMA_NODES.md` — how
  to create new concept nodes
- `.claude/skills/project-manager/references/VALIDATION.md` — the
  validation gate
- `.claude/skills/agent-messaging/SKILL.md` — how to talk to the
  human via MCP
