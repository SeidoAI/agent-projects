---
name: pm-rescope
description: Expand an existing project's scope with new intent or planning docs.
argument-hint: "<free-text new-scope description, optional path to new planning docs>"
---

You are the project manager for this repository. Load the project-manager
skill if not active, then execute the **Initial Scoping** workflow in
`.claude/skills/project-manager/references/WORKFLOWS_INITIAL_SCOPING.md`
in **expand-existing mode**.

New scope request:
$ARGUMENTS

Rescoping differs from initial scoping because the project already has
content:

1. Run `keel brief` to load current project state.
2. Read the existing issues, concept nodes, and sessions so you know
   what's already scoped and what's in progress.
3. If the user's description references a new planning doc path, read
   those files.
4. Identify what the new scope adds:
   - **New issues** to create (allocate new keys via
     `keel next-key --type issue`)
   - **New concept nodes** to add
   - **Existing issues to modify** (priority changes, acceptance
     criteria updates, new references)
   - **Relationships** between new and existing items
     (`blocked_by`, `related`, `[[references]]`)
5. Do NOT delete or renumber existing items without explicit user
   permission. Incremental growth only.
6. Write the new files and update the existing ones.
7. Run `keel validate --strict`. Fix errors.
8. Commit with a message describing the rescope (e.g.
   `rescope: add billing initiative with 8 new issues`).

Rescoping is additive by default. If the user wants to drop work, they
should use `/pm-issue-close` or explicit `/pm-edit` commands.
