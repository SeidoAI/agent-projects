---
name: frontend-development
description: >-
  Development skill for a TypeScript/React frontend repo in a tripwire.
  Covers branching, test-driven development, commit patterns,
  code-quality checks, tripwire interaction (reading issues, writing
  comments, maintaining concept nodes), and completion artifacts. Use
  when implementing UI features, fixing frontend bugs, creating
  components, or making any code changes in a frontend repo referenced
  by the project.
license: MIT
metadata:
  author: tripwire
  version: "1.0"
compatibility: >-
  React 18+, TypeScript 5+, Vite or Next.js, Node.js 20 LTS+. Adapts
  to whatever the repo uses for lint/format (Biome / ESLint+Prettier),
  testing (Vitest / Jest + React Testing Library), and styling
  (Tailwind / CSS modules / styled-components). Assumes a git-based
  repo with a long-lived `test` (or `develop`) branch.
---

# Frontend Development

You are a frontend coding agent in a tripwire. Given issue keys and
allowed repos, your job is to implement, test, and open a PR.

## The project layer

The PM skill writes issue/node/session files; you consume them. You
write:

- **Code** in the target repo (branching from `test` or `main`).
- **Session artifacts** in `<project>/sessions/<id>/artifacts/`:
  `plan.md`, `task-checklist.md`, `verification-checklist.md`,
  `recommended-testing-plan.md`, `post-completion-comments.md`.
- **Concept nodes** in `<project>/nodes/` for new artifacts that other
  issues will reference (component contracts, hook signatures,
  routing decisions).
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
state; the PM will pick it up.

## Common commands

Adapt to whatever the target repo's `package.json` defines. Typical:

```bash
# Install
npm install                 # or pnpm install / yarn

# Local dev
npm run dev                 # Vite/Next dev server

# Build
npm run build               # production bundle
npm run preview             # preview built bundle (Vite)

# Code quality
npm run lint                # whatever lint script the repo defines
npm run format              # if defined

# Tests
npm test                    # one-shot
npm run test:watch          # watch mode
npm run test:coverage       # with coverage
```

If the repo uses Biome, prefer `npx biome check .` /
`npx biome check --write .`. If it uses ESLint + Prettier, use the
scripts in `package.json` rather than calling them directly.

## Workflow: picking up an issue

### Phase 1: Discovery

1. Read the issue (`<project>/issues/<KEY>/issue.yaml`) — full
   frontmatter + body. Note acceptance criteria.
2. Resolve every `[[reference]]` in the body by reading the matching
   `<project>/nodes/<id>.yaml`. Nodes carry the source paths and
   current content hashes.
3. Check `blocked_by`: every dep must be `completed` (or `verified`
   per the project's policy). Otherwise stop and comment / send
   `stuck`.
4. Clone the target repo if needed; check out the base branch
   (usually `test`).

### Phase 2: Planning

5. `tripwire project brief` to front-load context.
6. Read the source at each node path. Understand existing components,
   hooks, contexts, and patterns before designing anything new.
7. Write `plan.md` to `<project>/sessions/<session-id>/artifacts/`,
   per `<project>/templates/artifacts/plan.md.j2`. Reference nodes
   via `[[node-id]]`.
8. Write initial `task-checklist.md`
   (`templates/artifacts/task-checklist.md.j2`).
9. Write initial `verification-checklist.md` — the list you'll walk
   at the end. For UI work, include manual browser-verification
   items (golden path + edge cases) alongside the automated checks.
10. If `manifest.yaml` has `plan` approval gate enabled, send a
    `plan_approval` message and STOP. The orchestrator re-engages.

### Phase 3: Setup

11. Branch from the base:
    ```bash
    git checkout test && git pull origin test
    git checkout -b <agent-id>/<KEY>-<slug>
    git push -u origin <agent-id>/<KEY>-<slug>
    ```
    e.g. `claude/SEI-42-graph-zoom`.
12. Mark the first task `in_progress` in `task-checklist.md`. Send
    a `status` message with state `implementing`.

### Phase 4: Implementation

13. **Test-driven.** Write tests first with the repo's test framework
    (Vitest/Jest + React Testing Library); commit red. Implement;
    commit green.
14. Commit in logical units:

    | Commit | Scope |
    |---|---|
    | 1 | Tests (red) |
    | 2 | Components / hooks / contexts (implementation) |
    | 3 | Routing & wiring (route registration, layout integration) |
    | 4 | Docs in `docs/issues/<KEY>/` |

15. After each commit:
    ```bash
    npm run lint
    npm test
    npm run build
    ```
16. Update `task-checklist.md` per row. Send `status` on every state
    transition (`implementing` → `testing` etc.).
17. Create or update concept nodes for any new artifacts other
    issues will reference (component contracts, hook signatures,
    routing decisions). Schemas: PM skill's `SCHEMA_NODES.md` +
    `examples/node-*.yaml`.
18. Rehash any existing node whose source you touched (new SHA-256
    → `source.content_hash`).

### Phase 5: Verification

19. Walk `verification-checklist.md` to ✓ or ✗ on every item; fix
    and re-run on any ✗.
20. **Browser verification.** Start the dev server (`npm run dev`)
    and exercise the feature in a real browser — golden path first,
    then edge cases. Type checking and unit tests verify *code*
    correctness; only the browser verifies *feature* correctness.
    If you cannot run the browser (sandbox/headless env), say so
    explicitly in `verification-checklist.md` rather than claiming
    success.
21. Target-repo checks: `npm run lint`, `npm test`, `npm run build`.
    All must pass. (Project-side validate is the
    `tripwire session transition` gate — see Phase 6.)
22. `tripwire node refs check` — no dangling or stale refs in anything
    you wrote.

### Phase 6: Delivery

24. Write `recommended-testing-plan.md` — what the human reviewer
    should test beyond CI (visual regressions, browser/device
    matrix, a11y spot-checks).
25. Write `post-completion-comments.md` — decisions, deferrals,
    surprises, PM follow-ups.
26. Write `<project>/issues/<KEY>/developer.md` — implementation
    summary, scope, testing instructions, risks. For UI work,
    include screenshots or a short clip of the feature where
    practical.
27. Write a completion comment to
    `<project>/issues/<KEY>/comments/<NNN>-completion-YYYY-MM-DD.yaml`
    (shape: `examples/comment-status-change.yaml`,
    `type: completion`).
28. Commit the project-repo changes (artifacts, nodes, comments,
    developer.md) per `COMMIT_CONVENTIONS.md`.
29. Push the target-repo branch.
30. `gh pr create` against the base branch. Title `[<KEY>] <short
    description>`. Body: summary + testing + node notes.
31. Send a `progress` message with the PR URL.
32. **Transition** — this is the v0.12 atomic validate gate:
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
33. Final `status` message: state `done`.

## Operating rules

**Architectural discipline.** No autonomous architectural decisions —
if the issue doesn't specify the approach (component-library choice,
state-management pattern, routing layout, styling system), send a
`question` message with options and STOP. Match surrounding code
style; don't refactor what the issue doesn't touch. Respect
`[[decision]]` nodes referenced in the issue body — those are locked.

**TDD.** Tests first, commit red; implementation second, commit green.
If an existing test breaks after your change, default assumption is
your change is wrong — investigate before rewriting the test. Never
disable a test to declare done. If you must rewrite a test, leave a
note in `post-completion-comments.md` explaining why.

**Code quality.** Lint and test before every commit
(`npm run lint && npm test`). Never commit secrets — no API keys,
tokens, or service-account keys in code. Public client config values
that a vendor explicitly documents as safe to ship (e.g. Firebase
`apiKey`, Stripe publishable keys) are safe to commit; private keys
and tokens are never safe. Format before committing.

**Security-sensitive changes** (auth flow, route guards, token
management, CSP, CORS) require extra scrutiny. If the issue doesn't
explicitly specify the security posture, send a `question` message
asking for clarification.

**Accessibility.** Components must meet the baseline in
`references/PATTERNS.md` § Accessibility — semantic HTML, ARIA on
interactive elements, keyboard reachable, WCAG AA contrast. The
linter's a11y rules are part of the lint gate.

**Scope.** Do what the issue says. No surrounding refactors, no
unrequested features, no "improvements". Out-of-scope findings go in
`fyi` messages or `post-completion-comments.md`. No premature
abstraction — three similar lines beats a helper you'll never reuse.

**Messaging.** `status` every ~5 min of active work and on every state
transition. `blocking` priority only for `plan_approval`, `question`,
`stuck`, `escalation`, `handover`. Always `check_messages()` after
re-engagement — responses don't show up in context automatically.

## Implementation references (progressive disclosure)

Load only the reference you need:

- `references/ARCHITECTURE.md` — typical SPA architecture: routing,
  state management, auth flow, API integration, build config,
  runtime configuration.
- `references/PATTERNS.md` — component organisation, styling, API
  client, custom hooks, dev mode, error boundaries, accessibility,
  testing strategy, runtime config.
- `references/DECISIONS.md` — how locked architectural decisions are
  tracked in tripwire (via `[[decision]]` nodes), and a starter
  checklist of the technology choices a project should pin
  explicitly.

## See also

- `.claude/skills/project-manager/references/SCHEMA_ARTIFACTS.md` —
  the artifact schemas you must produce.
- `.claude/skills/project-manager/references/SCHEMA_NODES.md` — how
  to create new concept nodes.
- `.claude/skills/project-manager/references/VALIDATION.md` — the
  validation gate.
- `.claude/skills/agent-messaging/SKILL.md` — how to talk to the
  human via MCP.
- `.claude/skills/backend-development/references/COMMIT_PATTERN.md`
  — the project-wide commit convention (applies to frontend too).
- `.claude/skills/backend-development/references/TDD.md` — TDD
  discipline with examples.
