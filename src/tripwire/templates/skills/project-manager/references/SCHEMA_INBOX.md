# Inbox entry schema

The inbox surfaces items that need the user's attention or knowledge.
Entries live at `<project>/inbox/<id>.md` — one markdown file per
entry, YAML frontmatter + free-form markdown body.

The PM agent is the only authorized writer (see SKILL.md "Inbox").

## File path

```
<project>/inbox/<id>.md
```

`<id>` follows `inb-YYYY-MM-DD-<short>` — chronological by file name,
short suffix prevents same-day collisions.

## Frontmatter

| Key | Type | Notes |
|---|---|---|
| `id` | string | `inb-YYYY-MM-DD-<short>` (matches the filename) |
| `uuid` | string | RFC 4122 v4 — allocate via `tripwire uuid` |
| `created_at` | ISO timestamp | `2026-04-27T15:42:00Z` |
| `author` | string | `pm-agent` for now |
| `bucket` | enum | `blocked` or `fyi` |
| `title` | string | One-line headline shown in the dashboard list |
| `references` | typed list | See below |
| `escalation_reason` | string | Short slug seeding future meta-learning |
| `resolved` | bool | Always `false` on write — human resolves via UI |
| `resolved_at` | ISO timestamp \| null | `null` on write |
| `resolved_by` | string \| null | `null` on write |

## When to write each bucket

`bucket: blocked` (interruptive, demands action) — write when:

- A scope/quality decision exceeds your authority (split this issue?
  extend this session? approve this $X spend?)
- A session is paused waiting on external input (PR review comment
  needing the user's call, ambiguity in plan.md the user has to
  resolve)
- A validator failure that requires architecture intervention (not
  just a fix you can dispatch)
- A cost crosses a configured approval threshold

`bucket: fyi` (digest, "you should know in case you disagree") — write
when:

- A session merges (with cost + re-engagement summary)
- You auto-close an issue (superseded, deduped) where the user might
  disagree
- Validator clean after substantial change (positive signal)
- Throughput milestone (e.g. "5 sessions completed this week")
- Any decision YOU made that's worth reversing if the user disagrees

## Skip — do NOT write entries for

- Routine operations (creating issues, normal status transitions,
  spawning sessions)
- Things the validator already surfaces
- Things visible on the dashboard via other means (e.g. "session X
  is in_review" is already in the right column)
- Self-talk / scratchpad reasoning — the inbox is for the human, not
  your working memory

## `references` shape

Typed list (discriminated union). Supported entries:

- `{issue: SEI-42}`
- `{epic: SEI-30}`
- `{session: storage-impl}`
- `{node: auth-token-endpoint}` — content-hash freshness checked
- `{node: auth-token-endpoint, version: v3}` — pinned to v3, dashboard
  warns if the node has drifted past that version
- `{artifact: {session: storage-impl, file: plan.md}}`
- `{comment: {issue: SEI-42, id: cmt-2026-04-26-x9k}}`
- `{pr: SeidoAI/tripwire/123}`

Pin node versions when the entry's reasoning depends on a specific
snapshot of that node.

## `escalation_reason` slugs

Short slugs (no formal enum yet) — seed for meta-learning. We'll
mine which reasons earn fast resolution vs ignored-then-archived to
refine when escalation is appropriate.

Common values: `scope-creep`, `cost-approval`, `validator-block`,
`session-merged`, `issue-superseded`, `milestone`.

## Worked example

```markdown
---
id: inb-2026-04-27-a3f2
uuid: 7c5b1f9e-4a2d-4e6c-9b8f-1e3d5a7c9b0f
created_at: '2026-04-27T15:42:00Z'
author: pm-agent
bucket: blocked
title: Should SEI-42 be split into 3 issues?
references:
  - issue: SEI-42
  - session: storage-impl
  - node: auth-token-endpoint
    version: v3
escalation_reason: scope-creep
resolved: false
resolved_at: null
resolved_by: null
---

Scope crept during execution; SEI-42 now spans auth + storage + api.
Recommendation: split before re-engagement.

Options:
- Split into SEI-42a/b/c
- Extend the existing session (more cost, more risk of drift)

Picking the split is the user-decision-shaped reason this is
`bucket: blocked` rather than `fyi`.
```

## After writing

1. Run `tripwire validate`. The validator checks schema
   shape and that every entry in `references` resolves to a real
   entity (dangling refs are lint errors).
2. The file watcher emits a `FileChangedEvent` with
   `entity_type=inbox`. The dashboard re-renders within ~1s.

## Do not resolve your own entries

Leave `resolved: false`. The human clicks ✓ in the dashboard, which
calls the resolve endpoint and rewrites the file. Auto-resolving
defeats the purpose of the inbox.
