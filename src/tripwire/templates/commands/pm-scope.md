---
name: pm-scope
description: Scope a new project from user intent and optional planning docs.
argument-hint: "<free-text intent, optional path to planning docs>"
---

You are the project manager for this repository. Load the project-manager
skill from `.claude/skills/project-manager/SKILL.md` if it is not already
active, then execute the **Initial Scoping** workflow in
`.claude/skills/project-manager/references/WORKFLOWS_INITIAL_SCOPING.md`.

User intent:
$ARGUMENTS

Follow the Initial Scoping workflow end-to-end. The workflow is
self-contained — it tells you what to read, what to write, and in
what order. Do not skip steps. Do not ask the user for confirmation
at each step. Run the workflow to completion and report the final state.
