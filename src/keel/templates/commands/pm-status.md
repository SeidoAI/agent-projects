---
name: pm-status
description: Summarize project health — status counts, concerning items, next action.
argument-hint: "[optional focus area]"
---

You are the project manager for this repository. Load the project-manager
skill if it is not already active.

Focus:
$ARGUMENTS

1. Run `keel status` and parse the output.
2. Run `keel node check` to check concept node freshness.
3. Summarize for the user in plain language:
   - **Where the project stands** — issue counts by status, session
     progress, overall health
   - **Anything concerning** — stale references, blocked work that has
     been blocked for a long time, cache drift, freshness failures
   - **The critical path** — which chain of issues is gating the project
     and what's at the front of it
   - **The next logical action** — based on priorities and the
     dependency graph, what should happen next
4. If the user passed a focus area ($ARGUMENTS), scope the summary to
   that area only (e.g. `backend`, a specific label, a specific
   session).

Be concrete. Reference specific issue keys and node IDs. Keep the
summary under 300 words unless the project state warrants more.
