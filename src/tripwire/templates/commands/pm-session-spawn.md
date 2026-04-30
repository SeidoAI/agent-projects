---
name: pm-session-spawn
description: Spawn a queued session locally via Claude Code subprocess.
argument-hint: "<session-id>"
fires_at: executing
---

You are the project manager. Load the project-manager skill if not
active.

Session to spawn:
$ARGUMENTS

Workflow:

1. Verify session exists and status is `queued`.
2. Run `tripwire session spawn $ARGUMENTS --dry-run` to preview the
   spawn (worktree paths, branch, max turns).
3. If dry-run passes, write a launch comment on each issue in
   `session.yaml.issues` (use `comment_templates/status_change.yaml.j2`).
   Body: "Session $ARGUMENTS spawned locally; branch <branch>".
4. Run `tripwire validate --strict`.
5. Commit: `spawn: $ARGUMENTS (local)`.
6. Run `tripwire session spawn $ARGUMENTS` (real spawn).
7. Report:
   - Session id, branch, worktree path
   - Log path and PID
   - `tail -f <log-path>` instructions
