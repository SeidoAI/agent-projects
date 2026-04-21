---
name: pm-project-sync
description: Pull workspace updates, mediate merges, then push local changes.
argument-hint: "[--pull-only] [--push-only] [--nodes=...]"
---

You are the project manager. Load the project-manager skill if not
active. Also read
`.claude/skills/project-manager/references/WORKSPACE_SYNC.md` — it
describes merge-brief structure and resolution strategy.

Flags:
$ARGUMENTS

Workflow:

1. Parse `$ARGUMENTS`:
   - `--pull-only` — pull from workspace, resolve merges, no push
   - `--push-only` — push local changes only (requires no pending briefs)
   - `--nodes=a,b,c` — restrict to specific nodes
   - default — bidirectional (pull, resolve, push)
2. Run `tripwire brief` to load project state.
3. Pull phase (skip if `--push-only`):
   a. Run `tripwire workspace pull [--nodes=...]`.
   b. Exit 0 — auto-merges applied, continue to step 5.
   c. Exit 10 — merges pending. Go to step 4.
   d. Other non-zero — report and stop.
4. Merge mediation (if step 3 returned exit 10):
   a. For each brief in `.tripwire/merge-briefs/*.yaml`:
      - Read the brief (`base_version`, `ours_version`, `theirs_version`,
        `field_diffs`, `auto_merged_fields`, `hints`).
      - Read the draft merge in `nodes/<node-id>.yaml` (starting point).
      - For each `field_diff.status == conflict`: pick a resolution
        informed by the hints + your understanding of project intent.
        Combine prose when both sides added distinct value; union lists
        when additions are independent; pick one when truly
        contradictory.
      - Edit `nodes/<node-id>.yaml` to the resolved form.
      - Run `tripwire workspace merge-resolve <node-id>` — validates the
        node, bumps `workspace_sha`, deletes the brief.
   b. If merge-resolve fails validation, fix the node file and retry.
5. Push phase (skip if `--pull-only`):
   a. Run `tripwire workspace push [--nodes=...]`.
   b. Exit 0 — done.
   c. Exit 11 — upstream diverged again (rare). Go back to step 3.
6. Run `tripwire validate --strict`; commit: `sync: <N> nodes with workspace`.
7. Report:
   - Number of nodes pulled + merges mediated + nodes pushed
   - New workspace_sha
   - Any forked/skipped nodes

This command is the single entry point for bidirectional sync. For
forking a specific node, use `tripwire workspace fork <id>` directly.
