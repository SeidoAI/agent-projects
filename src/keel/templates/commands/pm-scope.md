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

Before writing any files:

1. Run `keel brief` to load the current project state (next IDs, enums,
   templates, skill examples, validation gate command).
2. Read every `.md` file in `./planning/` as supplementary context on top
   of the user's intent above. `keel init` creates this directory by
   default; if it is empty or missing, proceed with the user's intent
   alone — do not ask the user to point at a path.
3. Follow the Initial Scoping workflow end-to-end:
   - Identify the set of issues, concept nodes, and sessions the project needs.
   - Allocate issue keys via `keel next-key --type issue` (one per issue).
   - Generate `uuid4`s in code for every entity.
   - Write issue files to `issues/`, concept nodes to `graph/nodes/`,
     sessions to `sessions/`.
   - Use the canonical examples in
     `.claude/skills/project-manager/examples/` as templates.
4. After each batch of file writes, run
   `keel validate --strict --format=json` and fix any errors the report
   surfaces.
5. When validation exits 0, commit the result with a single clear commit
   message (e.g. `scoping: initial project scope from raw planning docs`).

Do not ask the user for confirmation at each step. Run the workflow to
completion and report the final state.
