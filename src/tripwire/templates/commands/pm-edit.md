---
name: pm-edit
description: Apply a surgical update — status, comment, node, or session change.
argument-hint: "<free-text change description>"
---

You are the project manager. Load the project-manager skill from
`.claude/skills/project-manager/SKILL.md` if not active, then execute
the **Incremental Update** workflow in
`.claude/skills/project-manager/references/WORKFLOWS_INCREMENTAL_UPDATE.md`.

Change requested:
$ARGUMENTS

Before editing any files:

1. Run `tripwire brief` to load project state.
2. Parse the change description to identify the target entities
   (issue key, session, node ID) and the action (status change, add
   comment, create node, update session).
3. Read the target entity file(s) to confirm current state.
4. Apply the minimal set of edits needed.
5. If the change touches the concept graph (new `[[node]]` refs or
   a new node file), verify graph consistency via `tripwire refs check`.
6. Run `tripwire validate`. Fix any errors.
7. Commit with a focused message describing just this change.

Do not expand scope. Incremental updates stay surgical.
