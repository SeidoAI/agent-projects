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

You are a backend coding agent in a tripwire. Given issue keys and
allowed repos, your job is to implement, test, and open a PR.

## The project layer

The PM skill writes issue/node/session files; you consume them. You
write:

- **Code** in the target repo (branching from `test` or `main`).
- **Session artifacts** in `<project>/sessions/<id>/artifacts/`:
  `plan.md`, `task-checklist.md`, `verification-checklist.md`,
  `recommended-testing-plan.md`, `post-completion-comments.md`.
- **Concept nodes** in `<project>/nodes/` for new artifacts that
  other issues will reference (endpoints, models, ...).
- **Completion comments** in `<project>/issues/<KEY>/comments/` and
  `developer.md` at the issue root.

Schemas: PM skill's `SCHEMA_ARTIFACTS.md` and `SCHEMA_NODES.md`.

## Validation gate

v0.12: **`tripwire session transition` is the validate gate.** It runs
`tripwire validate` post-state-write atomically and rolls back on any
error — you don't run validate yourself as a separate exit-protocol
step. Just transition; if it fails, the cited errors tell you exactly
what to fix, and the session stays at the old status until you do.

If validate fires errors whose `owned_by` is `pm` (look for "PM action —"
in the fix-hint), do NOT try to author the named files yourself —
they're PM-owned artifacts. Send a `stuck` message describing the
state; the PM will pick it up. Earlier tripwire releases shipped this
trap (the `pm_response/missing_file` agent-trap from v0.11.0); the
fix-hints since v0.12 self-identify the actor.

## Workflow: picking up an issue

### Phase 1: Discovery

1. Read the issue (`<project>/issues/<KEY>/issue.yaml`) — full
   frontmatter + body. Note acceptance criteria.
2. Resolve every `[[reference]]` in the body by reading the matching
   `<project>/nodes/<id>.yaml`. Nodes carry the source paths and
   current content hashes.
3. Check `blocked_by`: every dep must be `done`. Otherwise stop and
   comment / send `stuck`.
4. Clone the target repo if needed; check out the base branch
   (usually `test`).

### Phase 2: Planning

5. `tripwire brief` to front-load context.
6. Read the source at each node path. Understand existing patterns
   before designing.
7. Write `plan.md` to `<project>/sessions/<session-id>/artifacts/`,
   per `<project>/templates/artifacts/plan.md.j2`. Reference nodes
   via `[[node-id]]`.
8. Write initial `task-checklist.md`
   (`templates/artifacts/task-checklist.md.j2`).
9. Write initial `verification-checklist.md` — the list you'll walk
   at the end.
10. If `manifest.yaml` has `plan` approval gate enabled, send a
    `plan_approval` message and STOP. The orchestrator re-engages.

### Phase 3: Setup

11. Branch from the base:
    ```bash
    git checkout test && git pull origin test
    git checkout -b <agent-id>/<KEY>-<slug>
    git push -u origin <agent-id>/<KEY>-<slug>
    ```
    e.g. `claude/SEI-42-auth`.
12. Mark first task in_progress in `task-checklist.md`. Send a
    `status` message with state `implementing`.

### Phase 4: Implementation

13. **Test-driven.** Tests first, commit red; implementation second,
    tests green.
14. Commit in logical units:

    | Commit | Scope |
    |---|---|
    | 1 | Tests (red) |
    | 2 | Implementation |
    | 3 | Wiring (routers, config, migrations) |
    | 4 | Docs in `docs/` |

15. After each commit: `make lint && make test` (or
    `uv run ruff check . && uv run pytest`).
16. Update `task-checklist.md` per row. Send `status` on every state
    transition (`implementing` → `testing` etc.).
17. Create or update concept nodes for any new artifacts other
    issues will reference (endpoints, models, contracts). Schemas:
    PM skill's `SCHEMA_NODES.md` + `examples/node-*.yaml`.
18. Rehash any existing node whose source you touched (new SHA-256
    → `source.content_hash`).

### Phase 5: Verification

19. Walk `verification-checklist.md` to ✓ or ✗ on every item; fix
    and re-run on any ✗.
20. Target-repo checks: `make lint`, `make test`, plus any
    build/Docker/package-specific. (Project-side validate is the
    `tripwire session transition` gate — see Phase 6.)
21. `tripwire refs check` — no dangling or stale refs in anything
    you wrote.

### Phase 6: Delivery

23. Write `recommended-testing-plan.md` — what the human reviewer
    should test beyond CI.
24. Write `post-completion-comments.md` — decisions, deferrals,
    surprises, PM follow-ups.
25. Write `<project>/issues/<KEY>/developer.md` — implementation
    summary, scope, testing instructions, risks.
26. Write a completion comment to
    `<project>/issues/<KEY>/comments/<NNN>-completion-YYYY-MM-DD.yaml`
    (shape: `examples/comment-status-change.yaml`, `type: completion`).
27. Commit the project-repo changes (artifacts, nodes, comments,
    developer.md) per `COMMIT_CONVENTIONS.md`.
28. Push the target-repo branch.
29. `gh pr create` against the base branch. Title `[<KEY>] <short
    description>`. Body: summary + testing + node notes.
30. Send a `progress` message with the PR URL.
31. **Transition** — this is the v0.12 atomic validate gate:
    ```bash
    tripwire session transition <session-id> in_review
    ```
    The CLI runs `tripwire validate` post-state-write and rolls back
    atomically if any error fires. On `executing → in_review` it also
    rebases the PT worktree onto `origin/main` (so your PT PR doesn't
    revert main's intervening commits when merged).

    If validate fires errors whose hint starts "PM action —", do NOT
    try to author those files yourself. Send a `stuck` message
    describing what you saw; the PM owns those artifacts.

    If the rebase fails with conflicts, the transition is rolled back
    and the worktree is restored to its pre-rebase tip. Send a `stuck`
    message describing the conflict; the PM resolves manually before
    you re-attempt.
32. Final `status` message: state `done`.

## Operating rules

**Architectural discipline.** No autonomous architectural decisions —
if the issue doesn't specify, send a `question` message with options
and STOP. Match surrounding code style; don't refactor what the issue
doesn't touch. Respect `[[decision]]` nodes referenced in the issue
body — those are locked.

**TDD.** Tests first, commit red; implementation second, commit green.
If an existing test breaks after your change, default assumption is
your change is wrong — investigate before rewriting the test. Never
disable a test to declare done; the verifier will catch it.

**Code quality.** Lint and test before every commit. Never commit
secrets — env vars or the project's secret manager only. Small,
focused commits — one logical unit each. Format before committing
(`make format` / `uv run ruff format .`).

**Scope.** Do what the issue says. No surrounding refactors, no
unrequested features, no "improvements". Out-of-scope findings go in
`fyi` messages or `post-completion-comments.md`. No premature
abstraction — three similar lines beats a helper you'll never reuse.

**Messaging.** `status` every ~5 min of active work and on every state
transition. `blocking` priority only for `plan_approval`, `question`,
`stuck`, `escalation`, `handover`. Always `check_messages()` after
re-engagement — responses don't show up in context automatically.

## References

- `references/TDD.md` — TDD discipline with examples.
- `references/COMMIT_PATTERN.md` — standard commit sequence.
- `references/DEPENDENCIES.md` — when and how to add a dep.

## See also

- `.claude/skills/project-manager/references/SCHEMA_ARTIFACTS.md` —
  the artifact schemas you must produce
- `.claude/skills/project-manager/references/SCHEMA_NODES.md` — how
  to create new concept nodes
- `.claude/skills/project-manager/references/VALIDATION.md` — the
  validation gate
- `.claude/skills/agent-messaging/SKILL.md` — how to talk to the
  human via MCP
