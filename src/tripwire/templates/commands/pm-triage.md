---
name: pm-triage
description: Process inbound suggestions and convert them into project changes.
argument-hint: "[optional item ID, or blank for all pending]"
---

You are the project manager for this repository. Load the project-manager
skill from `.claude/skills/project-manager/SKILL.md` if not active, then
execute the **Triage** workflow in
`.claude/skills/project-manager/references/WORKFLOWS_TRIAGE.md`.

Focus:
$ARGUMENTS

Before acting:

1. Run `tripwire brief` to load current project state.
2. Identify the inbound items to triage:
   - If the user passed a specific item ID, focus on that one.
   - Otherwise, gather all pending inbound items: unprocessed comments
     on issues, unread agent messages, post-completion suggestions,
     external bug reports.
3. For each inbound item, classify it as one of:
   - **Actionable now** → create issues / update existing / create nodes
   - **Needs more info** → ask a clarifying question via comment or message
   - **Duplicate** → link to existing item and close
   - **Won't do** → close with a reason comment
   - **Strategic** → surface for human review (do not auto-act)
4. Apply the appropriate action for each.
5. Run `tripwire validate`. Fix any errors.
6. Commit the triage result with a commit message summarizing what was
   processed.

Triage is about routing, not deep work. Keep each classification fast
and move on.
