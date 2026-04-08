# Backend Commit Pattern

The standard commit sequence for a backend issue. Each commit is a
logical unit that passes lint and tests on its own.

## The sequence

For a typical issue implementing one feature:

| # | Commit | Scope | Example message |
|---|---|---|---|
| 1 | Tests (red phase) | `tests/unit/test_<feature>.py`, `tests/integration/test_<feature>.py`, any `conftest.py` fixture updates | `test(SEI-42): add failing tests for auth token endpoint` |
| 2 | Implementation | `src/api/<feature>.py`, service/model changes | `feat(SEI-42): implement auth token endpoint` |
| 3 | Wiring | Router registration in `main.py`, middleware, config | `chore(SEI-42): wire auth router into main app` |
| 4 | Documentation | `docs/issues/<KEY>/developer.md`, README updates | `docs(SEI-42): add developer note for auth endpoint` |

Not every issue needs all four. Small bug fixes might be one commit
(tests + fix + docs together). Large features might have more
(tests, implementation broken into two steps, wiring, docs).

**Rule**: every commit must pass `make lint` and `make test` on its
own. If the tests fail at commit 1 (red phase), that's OK as long as
the LINT passes — the tests are documentation of the failure.
Actually preferred: have the tests commit be `test: add tests`, then
the next commit be `feat: implement the thing, tests now pass`.

## Commit message format

```
<type>(<ISSUE-KEY>): <short description>

<optional body with more context>

Refs: <ISSUE-KEY>
```

Types:
- `feat` — new feature
- `fix` — bug fix
- `test` — tests only
- `docs` — documentation only
- `refactor` — no behaviour change
- `chore` — wiring, config, dependencies
- `perf` — performance improvement

Examples:

```
feat(SEI-42): implement auth token endpoint

Adds POST /auth/token with JWT generation using python-jose.
Uses the existing [[user-model]] for credential lookup and
follows [[dec-003-session-tokens]] for cookie handling.

Refs: SEI-42
```

```
fix(SEI-51): handle expired refresh tokens gracefully

Previously a request with an expired refresh token returned a
500 because jwt.decode threw an uncaught ExpiredSignatureError.
Now we catch it and return 401 with the standard error envelope.

Refs: SEI-51
```

## Branch naming

`<agent-id>/<ISSUE-KEY>-<slug>`:

- `claude/SEI-42-auth-endpoint`
- `claude/SEI-51-refresh-fix`
- `codex/SEI-60-migration-script`

Use your actual agent id as the prefix (from the `agents/<id>.yaml`
definition).

## PR titles

`[<ISSUE-KEY>] <Short description>`:

- `[SEI-42] Implement auth token endpoint`
- `[SEI-51] Fix expired refresh token handling`

## One issue, one branch, one PR

Don't bundle multiple issues into one branch. If you find yourself
wanting to do that, the issues should probably be merged into one
issue first (via the PM skill's triage workflow).

## See also

- `TDD.md` — how the tests-first commit works
- `.claude/skills/project-manager/references/COMMIT_CONVENTIONS.md` —
  the PROJECT repo's commit conventions (different from the target
  code repo)
