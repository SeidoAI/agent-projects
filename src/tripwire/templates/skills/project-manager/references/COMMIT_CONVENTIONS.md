# Commit Conventions

Rules for branches, commits, and PRs in the project repo. These exist
so human reviewers and the PM agent can tell at a glance what a change
is about.

## Branch naming

Agents push to branches named `<agent-id>/<slug>`:

- `claude/initial-scoping-2026-04-07`
- `claude/SEI-42-refresh-endpoint`
- `pm/triage-inbound-bugs`
- `claude/api-endpoints-core-fix-lint`

When the branch is tied to a specific issue, include the issue key in
the slug. When it's a broader piece of work, use a descriptive slug.

## Commits

Within a PR, prefer **one commit per logical change**. A full initial
scoping run can be one commit ("Initial project scope from raw
planning docs"). A small bug fix can be one commit. Don't pile
unrelated changes into a single commit.

Commit message format:

```
<type>: <one-line subject>

<optional multi-line body>

Refs: <ISSUE-KEY> (if applicable)
```

Types: `feat`, `fix`, `docs`, `refactor`, `chore`, `scoping`.

Examples:

```
scoping: initial project scope from plans/

20 issues across 4 epics, 15 concept nodes, 3 sessions.
Validated clean.

Refs: PKB-1..PKB-20
```

```
fix: correct typo in [[user-model]] reference

Refs: SEI-42
```

## PR titles

Format: `[<KEY>] <one-line summary>` — or for scoping work,
`[scoping] <scope description>`.

Examples:

- `[SEI-42] Implement JWT authentication endpoint`
- `[scoping] Initial project scope from plans/`
- `[PKB-18] Add Firestore user model`

## PR body

Use a section-heavy structure so reviewers can skim:

```markdown
## Summary
<1-3 sentences — what changed, why>

## Touched
- issues/SEI-42.yaml (new)
- nodes/auth-token-endpoint.yaml (new)
- sessions/api-endpoints-core/artifacts/plan.md (new)

## Validator
`tripwire validate --strict` exits 0.

## Concept graph
- Created [[auth-token-endpoint]] pointing at src/api/auth.py:45-82
- Rehashed [[user-model]] after touching src/models/user.py

## Follow-ups
- (Any deferred work, referenced by issue key if created)
```

## What goes in one PR

- **Initial scoping** — one PR for the whole scoping job.
- **One issue's work** — one PR (issue + plan + artifacts + any new
  nodes).
- **Triage** — one PR per triage pass (batch of small updates).
- **PM review response** — one PR per fix cycle.

Don't mix feature work and unrelated housekeeping in one PR.

## See also

- `WORKFLOWS_REVIEW.md` — the PM review side of PRs
- `ANTI_PATTERNS.md` — anti-patterns around commits and PRs
