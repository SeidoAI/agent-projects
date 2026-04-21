# Branch naming convention

Sessions use per-session branches. A session = one branch = one PR.
Issues contained in a session are mentioned in commits and the PR
description; they are **not** part of the branch name.

## Format

```
<type>/<session-slug>
```

- **`<type>`** — one of `feat`, `fix`, `refactor`, `docs`, `chore`,
  `test`. Derived from the session's **primary issue** (first item
  in `session.yaml.issues[]`) `kind` field, or explicit via
  `session.yaml.kind` override.
- **`<session-slug>`** — the session's ID with the `session-`
  prefix stripped.

## Examples

| Session ID | Primary issue kind | Branch |
|---|---|---|
| `session-infra-gcs` | feat | `feat/infra-gcs` |
| `session-correct-sort-order` | fix | `fix/correct-sort-order` |
| `session-extract-store` | refactor | `refactor/extract-store` |
| `session-bump-pydantic` | chore | `chore/bump-pydantic` |

## Rules

- **One branch per session.** Multi-issue sessions get one branch
  that closes all contained issues on merge.
- **Same branch name across all repos** in a multi-repo session.
- **No personal prefixes** (`maia/`, `claude/`).
- **Length ≤ 60 chars.**
- **Lowercase, hyphens only.** No underscores, no camelCase.

## How to get the canonical name

```bash
tripwire session derive-branch <session-id>
```

Its output is the exact branch name — use it verbatim; don't guess.

## Enforcement

- `handoff.yaml.branch` is validated against this pattern at session
  launch (`/pm-session-queue`).
- `tripwire lint handoff` flags any branch that doesn't match.
- The Pydantic `SessionHandoff` model rejects invalid branches at
  parse time.

## PR mapping

- 1 session = 1 branch = 1 PR.
- PR title: `<type>(<session-slug>): <session summary>`
  - Example: `feat(infra-gcs): set up GCS bucket infrastructure`.
- PR description lists each issue in the session with its resolution.
