---
name: pm-session-queue
description: Transition session to queued after readiness check.
argument-hint: "<session-id>"
---

You are the project manager. Load the project-manager skill if not
active.

Session to queue:
$ARGUMENTS

Workflow:

1. Run `tripwire session check $ARGUMENTS` to verify launch-readiness.
   If exit code is non-zero, report the punch list and stop. Do NOT
   proceed with outstanding errors.
<<<<<<<< HEAD:src/tripwire/templates/commands/pm-session-launch.md
2. Run `tripwire lint handoff $ARGUMENTS` and surface findings. Any
   error-severity finding blocks launch.
3. Run `tripwire brief` to load project state.
========
2. Run `tripwire lint handoff $ARGUMENTS` and surface findings. Any
   error-severity finding blocks queueing.
3. Run `tripwire brief` to load project state.
>>>>>>>> origin/main:src/tripwire/templates/commands/pm-session-queue.md
4. Read `sessions/$ARGUMENTS/session.yaml` and `handoff.yaml`.
5. Run `tripwire session queue $ARGUMENTS`. This validates readiness and
   transitions `planned` → `queued`.
6. Update issue status on every issue in `session.yaml.issues`:
   - `ready` → `in_progress`
   - Add a comment on each issue pointing at the session (use
     `comment_templates/status_change.yaml.j2`).
7. Write a launch comment in
   `sessions/$ARGUMENTS/comments/001-queued-<YYYY-MM-DD>.yaml` using
   `comment_templates/status_change.yaml.j2`. Body: one paragraph
   summarising the handoff — reference `handoff.yaml.branch`, the
   agent type, and any open questions.
<<<<<<<< HEAD:src/tripwire/templates/commands/pm-session-launch.md
9. Run `tripwire validate --strict`. Fix any errors.
10. Commit: `launch: $ARGUMENTS → <agent-type>`.
11. Report the branch name (from `handoff.yaml.branch`) so the user
    or orchestration runtime can dispatch the execution agent.
========
8. Run `tripwire validate --strict`. Fix any errors.
9. Commit: `queue: $ARGUMENTS → <agent-type>`.
10. Report the branch name (from `handoff.yaml.branch`) so the user
    can dispatch the execution agent or run `/pm-session-spawn`.
>>>>>>>> origin/main:src/tripwire/templates/commands/pm-session-queue.md

Do NOT create `task-checklist.md`, `recommended-testing-plan.md`, or
`post-completion-comments.md`. Per `templates/artifacts/manifest.yaml`
these are owned by `execution-agent` and created during implementing /
completion phases.

Do NOT create the session itself. If it doesn't exist, tell the user
to run `/pm-session-create <issue-key>` first.
