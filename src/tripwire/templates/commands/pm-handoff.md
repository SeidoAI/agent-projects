---
name: pm-handoff
description: DEPRECATED — use /pm-session-create or /pm-session-queue.
argument-hint: "<issue-key-or-session-id>"
---

`/pm-handoff` is deprecated as of v0.6a and will be removed in v0.7.

Its old dual-mode behaviour has been split into two explicit
commands:

- `/pm-session-create <issue-key> [agent-type]` — scaffold a new
  session for an issue (formerly the implicit first half of handoff).
- `/pm-session-queue <session-id>` — transition an existing
  session from `planned` to `queued` (formerly the implicit second
  half).

Choose based on your starting state:

- **I have an issue and need a session for it**: run
  `/pm-session-create $ARGUMENTS` (assuming `$ARGUMENTS` is an issue
  key like `AUTH-42`).
- **I already have a session and need to launch it**: run
  `/pm-session-queue $ARGUMENTS` (assuming `$ARGUMENTS` is a session
  id like `session-auth-42-setup`).

If `$ARGUMENTS` is ambiguous (could be either), tell the user to
re-run with the explicit command. Do not guess.
