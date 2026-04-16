---
name: pm-project-create
description: Create a new project; auto-links to workspace if detected.
argument-hint: "<project-name> [--copy-nodes=...] [--path=...]"
---

You are the project manager. Load the project-manager skill from
`.claude/skills/project-manager/SKILL.md` if not active.

Arguments:
$ARGUMENTS

Workflow:

1. Parse `$ARGUMENTS`. First positional is the project name. Flags:
   - `--copy-nodes=a,b,c` — workspace node ids to pull into the new project
   - `--path=<dir>` — where to create it (default: sibling of cwd)
   - `--workspace=<path>` — explicit workspace (default: detect from cwd)
   - `--no-workspace` — force standalone project (skip workspace linking)
2. Determine workspace context:
   - If `--workspace=<path>`, use that.
   - Else if cwd has `workspace.yaml` at root, use cwd.
   - Else walk up for a workspace.yaml; if none found, standalone project.
3. Run `keel init <name>` to scaffold the project directory. After init,
   if a workspace context was detected:
   a. `cd <new-project>` (so relative workspace pointers resolve).
   b. Run `keel workspace link <workspace-path> --slug <key-prefix-lowercased>`.
   c. If `--copy-nodes` given, run `keel workspace copy <node-ids...>`.
4. Report:
   - Project directory created
   - Workspace link status
   - Nodes copied (with workspace_sha)
5. Suggest next: `cd <new-project> && /pm-scope <intent>`.

This command does NOT scope the project — that is `/pm-scope`'s job.
It only scaffolds and (optionally) wires workspace connectivity.
