---
name: pm-session-create
description: Create a session for an issue and scaffold its plan.
argument-hint: "<issue-key> [agent-type]"
---

You are the project manager. Load the project-manager skill from
`.claude/skills/project-manager/SKILL.md` if not active.

Arguments:
$ARGUMENTS

Workflow:

1. Parse `$ARGUMENTS`. First token is the issue key. Optional second
   token is the agent type (e.g. `backend-coder`, `frontend-coder`,
   `verification-agent`). If missing, infer from the issue's `agent`
   field or labels.
2. Run `keel brief` to load project state.
3. Read `issues/<issue-key>/issue.yaml`. Verify:
   - Status is `todo` or `ready`.
   - All `blocked_by` dependencies are `done`.
   - Referenced concept nodes exist and are fresh.
   If any check fails, report why and stop.
4. Allocate a session key: `keel next-key --type session`.
5. Create `sessions/<session-key>/` with:
   - `session.yaml` (from `session_templates/default.yaml.j2`) —
     include the issue key in `issues:` and the agent type.
   - `plan.md` (from `templates/artifacts/plan.md.j2`) — scope,
     approach, tasks grounded in the issue.
   - `verification-checklist.md` (from its template) — per
     `templates/artifacts/manifest.yaml` this artifact is PM-owned
     at planning phase.
6. Derive the canonical branch: `keel session derive-branch <session-key>`.
   Its output is the exact `<type>/<slug>` branch name.
7. Write `sessions/<session-key>/handoff.yaml` from
   `session_templates/handoff.yaml.j2` with:
   - `branch` = output of step 6
   - `open_questions` = anything you couldn't answer during scoping
   - `context_to_preserve` = decisions made during scoping
8. Run `keel validate --strict`. Fix any errors.
9. Commit: `session: create <session-key> for <issue-key>`.
10. Report the session directory path and run
    `/pm-session-check <session-key>` so the user sees readiness.

Do NOT create `task-checklist.md`, `recommended-testing-plan.md`, or
`post-completion-comments.md`. Per `templates/artifacts/manifest.yaml`,
these are owned by `execution-agent` and produced at later phases.

Do NOT transition session status to `queued`. Handoff is a separate
step via `/pm-session-launch`.
