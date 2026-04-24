# Keel v0.6 (addendum) — Git worktrees for session isolation

**Status**: design proposal
**Date**: 2026-04-16
**Amends**: `2026-04-15-pm-session-spawn-and-agenda.md` §2 (session spawn)
**Context**: discovered while preparing to launch two parallel keel-ui
sessions against the same repo

---

## 1. The problem

Sessions map 1:1 to branches. But git only allows one branch checked
out per clone. Two parallel sessions targeting the same repo cannot
run in the same working directory — the second `git switch` destroys
the first session's working state.

Current workaround: clone the repo twice. Wasteful (duplicates the
full object store) and error-prone (two remotes to keep in sync).

## 2. The fix

`keel session spawn` creates a **git worktree** per repo per session.
Each executing agent gets its own isolated directory with its own
branch, sharing the same `.git` database. Zero overhead beyond file
copies; commits from any worktree are immediately visible in all
others.

This is not a new concept — git worktrees have existed since git
2.5 (2015). We're just wiring them into the session lifecycle.

## 3. Design

### 3.1 Worktree path convention

```
<repo-parent>/<repo-name>-wt-<session-slug>/
```

Example for session `foundation-packaging` against `~/Code/seido/projects/keel/`:

```
~/Code/seido/projects/keel-wt-foundation-packaging/
```

The `-wt-` infix makes worktrees visually distinct from clones in
directory listings. The session slug suffix ties the directory to
exactly one session.

If the path already exists (stale worktree from a failed prior run),
`--resume` reuses it; without `--resume`, refuse and suggest cleanup.

### 3.2 Lifecycle

```
keel session spawn <id>
  1. readiness checks (unchanged from spawn spec)
  2. for each repo in session.yaml.repos[]:
       git -C <local-clone> worktree add <wt-path> -b <branch> <base_branch>
  3. spawn claude -p in the worktree directory (not the main clone)
  4. record wt-path in session.yaml.runtime_state.worktrees[]

keel session complete <id>  (or on PR merge)
  1. for each worktree in runtime_state.worktrees[]:
       git -C <local-clone> worktree remove <wt-path>
  2. clear runtime_state.worktrees[]

keel session cleanup [--all | <id>]
  1. remove worktrees for dead/failed sessions
  2. prune via `git worktree prune` to clean stale refs
```

### 3.3 Schema addition

`session.yaml.runtime_state` gains:

```yaml
runtime_state:
  worktrees:                              # NEW: one entry per repo
    - repo: SeidoAI/keel
      clone_path: ~/Code/seido/projects/keel
      worktree_path: ~/Code/seido/projects/keel-wt-foundation-packaging
      branch: feat/foundation-packaging
  # existing fields unchanged:
  claude_session_id: null
  log_path: null
  spawn_kind: null
```

`worktrees` is a list because multi-repo sessions (e.g. the v0.6
workspace spec's `infra-gcs-setup` example with two repos) need one
worktree per repo.

### 3.4 Multi-repo sessions

Session with repos `[SeidoAI/keel, SeidoAI/keel-infra]`:

```
~/Code/seido/projects/keel-wt-infra-gcs/        # worktree for keel
~/Code/seido/projects/keel-infra-wt-infra-gcs/   # worktree for keel-infra
```

The spawned agent's working directory is the **first** repo's
worktree (primary repo). The agent `cd`s to other worktrees as
needed per the plan steps.

### 3.5 What `keel session spawn` changes (amending the spawn spec)

In §2.2 step 4 of the spawn spec, replace:

> 4. Cut the branch in the target repo (`git -C <local> switch -c
>    <branch> <base_branch>`)

With:

> 4. Create a worktree: `git -C <local-clone> worktree add <wt-path>
>    -b <branch> <base_branch>`. Record `<wt-path>` in
>    `runtime_state.worktrees[]`.

In §2.2 step 5, the `claude -p` invocation runs in `<wt-path>`, not
`<local-clone>`.

In §2.3, the `nohup claude -p ...` cwd is the worktree path.

In §2.5, `runtime_state.workspace_volume` is replaced by the richer
`runtime_state.worktrees[]` list.

### 3.6 Why not use the Agent tool's `isolation: "worktree"` mode?

Claude Code's Agent tool has built-in worktree isolation for
subagents. We don't use it because:

1. We're spawning **top-level** `claude -p` sessions, not subagents.
2. We want the worktree lifecycle tied to the **keel session**
   lifecycle, not to a single agent tool call.
3. We want the path convention and metadata tracked in
   `session.yaml`, not ephemeral.

That said, if a spawned session internally uses the Agent tool with
`isolation: "worktree"` for its own sub-tasks, that's fine — nested
worktrees from worktrees work in git.

## 4. Error cases

| Code | Trigger | Fix hint |
|---|---|---|
| `spawn/worktree_path_exists` | directory already exists | `--resume` to reuse, or `keel session cleanup <id>` |
| `spawn/worktree_create_failed` | git worktree add failed (disk, permissions) | Check disk space and permissions on parent dir |
| `spawn/branch_checked_out` | branch already checked out in another worktree | Another session is using this branch; check `git worktree list` |
| `cleanup/worktree_dirty` | uncommitted changes in worktree | Commit or stash first, or `--force` to discard |

## 5. CLI additions

```
keel session spawn <id>       # creates worktree + spawns (amended)
keel session cleanup [<id>]   # removes worktree(s) for completed/failed sessions
keel session cleanup --all    # removes ALL session worktrees + prunes
```

`keel session cleanup` without args cleans up sessions in
`completed` or `failed` status only. `--all` cleans everything
(with confirmation prompt).

## 6. Testing

| Test | What it verifies |
|---|---|
| `test_spawn_creates_worktree` | worktree dir exists, branch checked out, `.git` is a file (not dir) |
| `test_spawn_two_sessions_parallel` | two sessions against same repo get separate worktrees, no interference |
| `test_spawn_multi_repo` | session with 2 repos gets 2 worktrees |
| `test_cleanup_removes_worktree` | dir gone, `git worktree list` no longer shows it |
| `test_cleanup_refuses_dirty` | uncommitted changes → error without `--force` |
| `test_spawn_resume_reuses_worktree` | existing worktree reused, no duplicate |
| `test_spawn_path_conflict` | stale worktree dir → clear error + hint |

## 7. Effort

~1.5 days on top of the session-spawn estimate (was 8.5 → now 10).
Most of the work is in `keel session spawn` (already being built)
and `keel session cleanup` (new, small).
