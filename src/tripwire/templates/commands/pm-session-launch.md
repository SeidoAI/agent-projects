---
name: pm-session-launch
description: Transition session to queued after readiness check.
argument-hint: "<session-id>"
---

You are the project manager. Load the project-manager skill if not
active.

Session to launch:
$ARGUMENTS

Workflow:

1. Run `tripwire session check $ARGUMENTS` to verify launch-readiness.
   If exit code is non-zero, report the punch list and stop. Do NOT
   proceed with outstanding errors.
2. Run `tripwire lint handoff $ARGUMENTS` and surface findings. Any
   error-severity finding blocks launch.
3. Run `tripwire brief` to load project state.
4. Read `sessions/$ARGUMENTS/session.yaml` and `handoff.yaml`.
5. Transition session status:
   - `planned` → `queued` (the expected happy path).
   - Reject any other starting status with a clear error.
6. Update `session.yaml.updated_at` to now.
7. Update issue status on every issue in `session.yaml.issues`:
   - `ready` → `in_progress`
   - Add a comment on each issue pointing at the session (use
     `comment_templates/status_change.yaml.j2`).
8. Write a launch comment in
   `sessions/$ARGUMENTS/comments/001-launch-<YYYY-MM-DD>.yaml` using
   `comment_templates/status_change.yaml.j2`. Body: one paragraph
   summarising the handoff — reference `handoff.yaml.branch`, the
   agent type, and any open questions.
9. Run `tripwire validate --strict`. Fix any errors.
10. Commit: `launch: $ARGUMENTS → <agent-type>`.
11. Report the branch name (from `handoff.yaml.branch`) so the user
    or orchestration runtime can dispatch the execution agent.

Do NOT create `task-checklist.md`, `recommended-testing-plan.md`, or
`post-completion-comments.md`. Per `templates/artifacts/manifest.yaml`
these are owned by `execution-agent` and created during implementing /
completion phases.

Do NOT create the session itself. If it doesn't exist, tell the user
to run `/pm-session-create <issue-key>` first.
