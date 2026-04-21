---
name: pm-session-agenda
description: Session-axis agenda with launch recommendations.
argument-hint: ""
---

You are the project manager. Load the project-manager skill if not
active.

Optional focus: $ARGUMENTS

Workflow:

1. Run `tripwire session agenda --format json`.
2. Summarise:
   - Session counts by status
   - Critical path
   - Top 3 launch recommendations with rationale
   - Any warnings (orphan blockers, stale sessions)
3. Reference specific session ids in your summary.
4. End with the literal commands to run next (e.g.
   `/pm-session-queue <id>` or `/pm-session-spawn <id>`).
