# Schema: Comments

Comments live under `issues/<KEY>/comments/`. Each comment is a
single YAML frontmatter + Markdown body file. The filename convention
is `<NNN>-<short-topic>-<YYYY-MM-DD>.yaml` where `NNN` is a
zero-padded sequence number within the issue.

Canonical example: `examples/comment-status-change.yaml`.

## Frontmatter fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `uuid` | UUID4 | yes | Agent-generated canonical identity. |
| `issue_key` | string | yes | The issue this comment is on. Must match an existing issue. |
| `author` | string | yes | Free-form handle (e.g. `claude`, `maia`, `pm-agent`). |
| `type` | string | yes | Must be in `enums/comment_type.yaml`. |
| `created_at` | ISO datetime | yes | |

## Comment types

From `enums/comment_type.yaml`:

- `status_change` — noting a change in issue state (e.g. "started
  work", "blocked by X", "marked done")
- `question` — asking for clarification or a decision
- `completion` — the final comment when an issue is done, summarising
  what was built
- `observation` — a finding or note worth preserving
- `decision` — recording an architectural or scoping decision

## Body

Free-form Markdown. Can reference concept nodes via `[[node-id]]` —
these are parsed and count toward the reference integrity check.

## Filename convention

`<project>/issues/<KEY>/comments/<NNN>-<short-topic>-<YYYY-MM-DD>.yaml`

- `NNN` — zero-padded sequence number (`001`, `002`, ...). Look at
  existing comments in the directory for the next number.
- `<short-topic>` — a kebab-case one-or-two-word summary.
- `<YYYY-MM-DD>` — ISO date.

Example: `issues/SEI-42/comments/003-blocked-rate-limiter-2026-04-07.yaml`.

## Creation rules

- Use the next free sequence number — don't reuse a number.
- If you're writing the first comment on an issue, the directory
  `issues/<KEY>/comments/` probably doesn't exist yet. Create it.
- `issue_key` must reference an existing issue — the validator catches
  dangling references.
- Don't invent `type` values — stick to the enum.

## See also

- `examples/comment-status-change.yaml`
- `WORKFLOWS_INCREMENTAL_UPDATE.md` — the flow for adding a comment
- `WORKFLOWS_TRIAGE.md` — when triage produces comments
