# Keel v0.6 (addendum) — Session spawn, agenda, and worktree isolation

**Status**: approved design
**Date**: 2026-04-16
**Supersedes**:
- `2026-04-15-pm-session-spawn-and-agenda.md`
- `2026-04-16-session-worktrees.md`
**Context**: final v0.6 changes — adds local session execution, a
session-axis agenda view, and git worktree isolation for parallel
sessions

---

## 1. Overview

Three gaps remain after the v0.6 workspace + PM workflow changes:

1. **No way to launch a planned session locally.** `pm-session-queue`
   (née `pm-session-launch`) transitions to `queued` for a future
   orchestrator. Nothing spawns an actual agent.
2. **No session-axis agenda.** `keel agenda` shows issues. There is
   no "which sessions are launchable, what's the critical path, what
   should I spawn first" view.
3. **No parallel session isolation.** Two sessions targeting the same
   repo cannot run in the same clone — the second `git switch`
   destroys the first's working state.

This spec solves all three as a single coherent feature: spawn
creates a worktree per repo, launches `claude -p` in it, and the
agenda tells you what to spawn next.

---

## 2. Session lifecycle

### 2.1 State transitions

```
planned ──[keel session queue]────→ queued
queued  ──[keel session spawn]───→ executing
executing ──[agent exits 0]──────→ completed
executing ──[agent exits non-0]──→ failed
executing ──[keel session pause]─→ paused
paused  ──[keel session spawn --resume]──→ executing
failed  ──[keel session spawn --resume]──→ executing
{planned,queued,executing,paused,failed} ──[keel session abandon]──→ abandoned
```

Terminal states: `completed`, `abandoned`.

### 2.2 New states

`paused` and `abandoned` are added to `enums/session_status.yaml`.

- **paused**: SIGTERM sent to the claude process. Worktree preserved.
  Claude Code's session file (JSONL conversation history) is
  preserved at its default location (`~/.claude/projects/...`).
  Resumable via `keel session spawn <id> --resume`.
- **abandoned**: deliberate decision to stop pursuing this session.
  Process killed if running. Worktree preserved until explicit
  `keel session cleanup <id>`. Not resumable — create a fresh
  session if work is needed.

### 2.3 Queue vs spawn

| | `keel session queue` | `keel session spawn` |
|---|---|---|
| Terminal status | `queued` | `executing` |
| Spawns process? | No | Yes |
| Requires local clone? | No | Yes |
| Requires `claude` CLI? | No | Yes |
| Purpose | Mark ready for execution | Execute locally |

Both run readiness checks. `queue` is the prep step; `spawn` is
the execution step.

---

## 3. Spawn

### 3.1 CLI

```
keel session spawn <session-id>
  [--project-dir PATH]
  [--max-turns-override N]   # override agent YAML default (default: 200)
  [--log-dir PATH]           # override default log location
  [--dry-run]                # print what would happen, don't spawn
  [--resume]                 # reuse existing worktree + claude session
```

### 3.2 Spawn flow

1. **Load session.yaml.** Verify status is `queued` (or
   `failed`/`paused` with `--resume`).
2. **Run readiness checks** (shared with `queue` and `session check`):
   - All `blocked_by_sessions` are `completed`
   - Required planning artifacts exist per `manifest.yaml`
   - `handoff.yaml` present and valid
   - Branch name in `handoff.yaml.branch` matches convention
3. **Local-spawn checks:**
   - Each repo in `session.yaml.repos[]` has a registered local
     clone (`project.yaml.repos[<slug>].local` exists on disk)
   - `claude` CLI is on PATH (`which claude`)
4. **Create worktrees** (one per repo in the session — see §4).
5. **Build and launch the `claude -p` invocation** (see §3.3).
   Capture PID. Generate a UUID for `claude_session_id` and pass
   it via `--session-id`.
6. **Update session.yaml:**
   - `status` → `executing`
   - `runtime_state.worktrees[]` populated (see §4.3)
   - `runtime_state.pid` set
   - `runtime_state.claude_session_id` set (UUID passed to claude)
   - `runtime_state.started_at` set
   - `runtime_state.log_path` set
   - Append to `engagements[]`
7. **Print launch summary** (session id, branch, worktree path, log
   path, PID, `tail -f` instructions).

### 3.3 The `claude -p` invocation

```bash
nohup claude -p "$(cat <plan-path>)

You are autonomous. Execute the plan above.
Stop only at the plan's stop-and-ask points.
Open a PR titled '<type>(<session-slug>): <session-name>' when done.
Report back as the final message." \
  --session-id <generated-uuid> \
  --max-turns <max-turns> \
  --output-format json \
  > <log-path> 2>&1 &
```

**Key decisions:**

- Plan content is **inlined** so the spawned session has it in
  context immediately.
- `--session-id` is a UUID we generate and store in
  `runtime_state.claude_session_id`. This enables resume.
- `--max-turns` precedence: CLI `--max-turns-override` > session's
  agent YAML `max_turns` field > hardcoded default of 200.
- No `--allowedTools` or `--append-system-prompt` — the spawned
  agent gets the full default toolset. Trust the plan to scope
  the work.

**Working directory**: the primary repo's worktree path (first
entry in `session.yaml.repos[]`). Multi-repo sessions: the agent
`cd`s to other worktrees as needed per plan steps.

**Log path**: `~/.keel/logs/<project-slug>/<session-id>-<timestamp>.log`.
Created on demand.

### 3.4 Resume

`keel session spawn <id> --resume`:

- Permitted when status is `failed` or `paused`.
- Reuses existing worktree (no new `git worktree add`).
- Passes `--session-id <stored_id> --resume` to `claude` so Claude
  Code restores the full conversation history.
- Appends a new `engagements[]` entry with `trigger: re_engagement`.

If the worktree no longer exists (manually deleted), spawn refuses
with `spawn/worktree_missing` and suggests `keel session cleanup`
then a fresh spawn without `--resume`.

### 3.5 Claude session persistence

Claude Code stores session files at
`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. These are
keyed by working directory, which means sessions spawned in a
worktree are stored under the worktree's encoded path.

We do **not** relocate these files into keel's session directory.
Instead, we record the `claude_session_id` (UUID) in
`runtime_state` — sufficient for resume via `--session-id`.

SIGTERM behavior: Claude Code uses append-only JSONL, so partial
writes are safe. The worst case is losing the last in-flight
message, not the whole conversation. This makes SIGTERM (pause)
a safe shutdown mechanism.

### 3.6 Exit codes

| Code | Meaning |
|---|---|
| 0 | Spawn succeeded, session is executing |
| 2 | Readiness check failed (reasons printed; nothing changed) |
| 3 | Local environment issue (missing clone, missing claude) |
| 4 | Branch already checked out in another worktree |

---

## 4. Worktree isolation

### 4.1 Why worktrees

Git only allows one branch checked out per clone. Two parallel
sessions targeting the same repo cannot coexist in the same working
directory. Git worktrees (since git 2.5) let multiple branches be
checked out simultaneously, sharing the same `.git` database.

### 4.2 Path convention

```
<repo-parent>/<repo-name>-wt-<session-slug>/
```

Example for session `foundation-packaging` against
`~/Code/seido/projects/keel/`:

```
~/Code/seido/projects/keel-wt-foundation-packaging/
```

The `-wt-` infix makes worktrees visually distinct from clones.

### 4.3 All-repos worktree

Spawn creates one worktree per repo in the session. A session with
repos `[SeidoAI/keel, SeidoAI/keel-infra]` produces:

```
~/Code/seido/projects/keel-wt-infra-gcs/
~/Code/seido/projects/keel-infra-wt-infra-gcs/
```

### 4.4 Schema: `runtime_state.worktrees[]`

```yaml
runtime_state:
  worktrees:
    - repo: SeidoAI/keel
      clone_path: ~/Code/seido/projects/keel
      worktree_path: ~/Code/seido/projects/keel-wt-foundation-packaging
      branch: feat/foundation-packaging
  pid: 12345
  claude_session_id: "a1b2c3d4-..."
  started_at: 2026-04-16T10:30:00Z
  log_path: ~/.keel/logs/keel-ui/foundation-packaging-20260416T103000.log
```

### 4.5 Why not Claude Code's `isolation: "worktree"` mode

Claude Code's Agent tool has built-in worktree isolation for
subagents. We don't use it because:

1. We spawn **top-level** `claude -p` sessions, not subagents.
2. We want the worktree lifecycle tied to the **keel session**
   lifecycle, not to a single agent tool call.
3. We want the path convention and metadata tracked in
   `session.yaml`, not ephemeral.

---

## 5. Pause, abandon, cleanup

### 5.1 Pause

```
keel session pause <id> [--project-dir PATH]
```

1. Verify status is `executing`.
2. Send SIGTERM to `runtime_state.pid`.
3. Update session.yaml: status → `paused`.
4. Worktree and claude session file preserved.

If PID doesn't exist (process already dead): set status to `failed`
instead, with a warning.

### 5.2 Abandon

```
keel session abandon <id> [--project-dir PATH]
```

1. If status is `executing`: SIGTERM the process.
2. Set status → `abandoned`.
3. Worktree preserved until explicit cleanup.

Refuses if status is already `completed` or `abandoned`.

### 5.3 Cleanup

```
keel session cleanup [<id>] [--all] [--force] [--project-dir PATH]
```

**Without args**: cleans sessions in `completed` or `abandoned`
status — removes worktrees and clears `runtime_state.worktrees[]`.

**With `<id>`**: cleans that specific session (with confirmation if
`executing` or `paused`).

**`--all`**: cleans every session's worktrees (with confirmation).

**`--force`**: skip dirty-worktree check (uncommitted changes
normally block cleanup).

**Flow per session:**

1. Check worktree exists on disk.
2. Check for uncommitted changes (abort unless `--force`).
3. `git -C <clone> worktree remove <wt-path>`.
4. Clear `runtime_state.worktrees[]` in session.yaml.
5. Run `git worktree prune` on each affected clone.

**Failed and paused sessions require explicit `<id>`** — they are
not cleaned by the default (no-args) invocation. Failed sessions
may be resumed; paused sessions are by definition intended to
continue.

No automatic cleanup on session completion. The worktree may
contain useful state (logs, uncommitted experiments). The user or
PM agent runs cleanup explicitly.

---

## 6. Session agenda

### 6.1 Purpose

Answer: "what should I launch next, and in what order?"

### 6.2 CLI

```
keel session agenda [--project-dir PATH] [--format text|json]
                    [--status STATUS] [--wave N]
```

Default format: `text`.

### 6.3 Data source

Each `session.yaml` has `status` and `blocked_by_sessions` (list of
session IDs). The agenda reads all sessions and builds a dependency
DAG.

### 6.4 Computation

1. **Build adjacency**: `blocked_by_sessions` → directed edges.
2. **Detect cycles**: if found, exit 1 with error listing cycle
   members.
3. **Topological sort**: partition into waves — wave 0 has no
   blockers, wave 1 blocked only by wave 0, etc.
4. **Critical path**: longest chain through the DAG by session
   count.
5. **Launch recommendations**: primary key = "blast radius" (count
   of sessions transitively unblocked); tiebreaker = parallel
   availability.

### 6.5 Text output

```
keel-ui-init — 15 sessions
  ✓ 0 completed   ◐ 0 executing   ◯ 13 planned   ⏸ 2 blocked

  critical path: S3 → S5 → S7 (3 sessions)

Wave 0 (launchable now):
  S3  foundation-packaging     planned    no blockers
  S4  auth-spike               planned    no blockers

Wave 1:
  S5  api-endpoints            planned    blocked by: S3
  S6  frontend-shell           planned    blocked by: S3

Wave 2:
  S7  integration-testing      planned    blocked by: S5, S6

Recommended next:
  1. foundation-packaging   (unblocks 13, on critical path)
  2. auth-spike             (unblocks 5, parallel to #1)
```

### 6.6 JSON output

```json
{
  "project": "keel-ui-init",
  "totals": { "completed": 0, "executing": 0, "planned": 13, "blocked": 2 },
  "critical_path": ["foundation-packaging", "api-endpoints", "integration-testing"],
  "waves": [
    ["foundation-packaging", "auth-spike"],
    ["api-endpoints", "frontend-shell"],
    ["integration-testing"]
  ],
  "sessions": [
    {
      "id": "foundation-packaging",
      "status": "planned",
      "blocked_by": [],
      "dependents": ["api-endpoints", "frontend-shell"],
      "is_launchable": true,
      "wave": 0,
      "critical_path_position": 1
    }
  ],
  "recommendations": [
    {
      "session_id": "foundation-packaging",
      "rank": 1,
      "rationale": "On critical path; unblocks 13 sessions."
    }
  ]
}
```

### 6.7 Filters

- `--status=planned` — only show sessions matching this status.
- `--wave=0` — only show a specific wave.
- No filters by default — show everything.

### 6.8 Edge cases

- **No sessions**: "No sessions found."
- **All completed**: "All sessions complete."
- **Cycle detected**: exit 1, error listing cycle members.
- **Orphan blocker**: `blocked_by_sessions` references nonexistent
  session → warning (not error), treat as unblocked.

---

## 7. Slash commands

### 7.1 Rename: `pm-session-launch` → `pm-session-queue`

The existing command is renamed. It sets status to `queued` after
readiness checks. It does not spawn.

### 7.2 `/pm-session-spawn`

```yaml
---
name: pm-session-spawn
description: Spawn a queued session locally via Claude Code subprocess.
argument-hint: "<session-id>"
---
```

1. Validate session exists, status is `queued`.
2. Run `keel session spawn <session-id> --dry-run` to preview.
3. If dry-run passes, write a launch comment on each contained issue.
4. Run `keel validate --strict`.
5. Commit: "launch: <session-id> (local spawn)".
6. Run `keel session spawn <session-id>` (real spawn).
7. Report: session id, branch, worktree path, log path, PID.

### 7.3 `/pm-session-agenda`

```yaml
---
name: pm-session-agenda
description: Session-axis agenda with launch recommendations.
argument-hint: ""
---
```

1. Run `keel session agenda --format json`.
2. Summarise: counts, critical path, top 3 recommendations.
3. End with literal commands to run.

---

## 8. Shared infrastructure

### 8.1 `core/session_readiness.py`

Extracted from logic shared by `queue`, `spawn`, and `session check`.

```python
def check(
    project_dir: Path,
    session_id: str,
    *,
    kind: Literal["queue", "spawn", "check"],
) -> ReadinessReport:
    ...

@dataclass
class ReadinessReport:
    ready: bool
    must_fix: list[ReadinessIssue]
    warnings: list[ReadinessIssue]
```

`kind="spawn"` adds local-environment checks (clone present, claude
on PATH). `kind="queue"` and `kind="check"` skip those.

### 8.2 `core/git_helpers.py`

- `branch_exists(repo_path, branch_name) -> bool`
- `worktree_add(clone_path, wt_path, branch, base_branch)`
- `worktree_remove(clone_path, wt_path)`
- `worktree_prune(clone_path)`

### 8.3 `core/process_helpers.py`

- `is_alive(pid: int) -> bool` — `os.kill(pid, 0)` wrapped to
  return bool.
- `send_sigterm(pid: int) -> bool` — send SIGTERM, return whether
  process existed.

---

## 9. Error codes

| Code | Trigger |
|---|---|
| `spawn/not_queued` | Status isn't `queued` (or `failed`/`paused` without `--resume`) |
| `spawn/readiness_failed` | Readiness checks fail |
| `spawn/worktree_path_exists` | Worktree dir exists without `--resume` |
| `spawn/worktree_missing` | `--resume` but worktree no longer on disk |
| `spawn/worktree_create_failed` | `git worktree add` failed |
| `spawn/branch_checked_out` | Branch checked out in another worktree |
| `spawn/claude_not_on_path` | `which claude` empty |
| `spawn/repo_not_cloned` | Session repo has no local clone |
| `spawn/claude_launch_failed` | `claude -p` failed to start |
| `pause/not_executing` | Session isn't executing |
| `pause/process_not_found` | PID doesn't exist (process already dead) |
| `abandon/already_terminal` | Session is `completed` or `abandoned` |
| `cleanup/worktree_dirty` | Uncommitted changes without `--force` |
| `agenda/cycle_detected` | Circular dependency in `blocked_by_sessions` |
| `agenda/orphan_blocker` | Blocker references nonexistent session (warning) |

---

## 10. Testing

| Test | Verifies |
|---|---|
| `test_spawn_creates_worktree` | Worktree dir exists, branch checked out, `.git` is a file |
| `test_spawn_records_runtime_state` | session.yaml has worktrees[], pid, claude_session_id |
| `test_spawn_rejects_non_queued` | Status must be queued |
| `test_spawn_resume_reuses_worktree` | Existing worktree reused, passes --session-id |
| `test_spawn_two_sessions_parallel` | Two sessions get separate worktrees |
| `test_spawn_multi_repo` | Session with 2 repos gets 2 worktrees |
| `test_spawn_path_conflict` | Stale worktree → clear error + hint |
| `test_pause_sigterms_process` | Process receives SIGTERM, status → paused |
| `test_pause_preserves_worktree` | Worktree intact after pause |
| `test_pause_dead_process_sets_failed` | Dead PID → status becomes failed |
| `test_abandon_kills_and_marks` | Process killed, status → abandoned |
| `test_abandon_rejects_terminal` | Already completed/abandoned → error |
| `test_cleanup_removes_worktree` | Dir gone, `git worktree list` clean |
| `test_cleanup_default_skips_failed` | Default cleanup ignores failed sessions |
| `test_cleanup_default_skips_paused` | Default cleanup ignores paused sessions |
| `test_cleanup_refuses_dirty` | Uncommitted changes → error without --force |
| `test_agenda_builds_dag` | Correct wave assignment from blocked_by_sessions |
| `test_agenda_detects_cycle` | Circular deps → exit 1 |
| `test_agenda_orphan_blocker_warns` | Missing blocker → warning, unblocked |
| `test_agenda_all_completed` | "All sessions complete" message |
| `test_agenda_recommendations` | Correct ranking by blast radius |
| `test_queue_sets_status` | Queue validates readiness + sets status |

All spawn tests use a fake `claude` shim (shell script that sleeps
briefly and exits 0). Never spawn a real Claude session in tests.

---

## 11. CLI summary

| Command | Purpose |
|---|---|
| `keel session queue <id>` | Validate readiness, status → queued |
| `keel session spawn <id>` | Create worktree, launch claude -p, status → executing |
| `keel session spawn <id> --resume` | Reuse worktree + claude session |
| `keel session pause <id>` | SIGTERM claude, status → paused |
| `keel session abandon <id>` | Kill if running, status → abandoned |
| `keel session agenda` | DAG / wave / recommendation output |
| `keel session cleanup [<id>] [--all] [--force]` | Remove worktrees |

---

## 12. Non-goals

- Container-based orchestrator runtime (separate effort)
- Auto-clone of repos not already present locally
- Inter-session orchestration (auto-launch next on completion)
- Remote / cross-machine spawning
- Relocating Claude Code session files into keel project dirs
- Auto-cleanup on session completion
- Duration-based critical path (no time estimates available)

---

## 13. Migration

Purely additive. No data migration. New `runtime_state` fields are
optional. New status values (`paused`, `abandoned`) don't affect
existing sessions. `keel session agenda` works on any project with
sessions, no changes needed.

The only breaking change is the rename of `pm-session-launch` →
`pm-session-queue`. The old slash command file is replaced.
