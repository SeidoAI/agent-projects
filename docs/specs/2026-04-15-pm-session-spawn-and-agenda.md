# Keel v0.6 (addendum) — PM session-spawn + session-axis agenda

**Status**: design proposal, ready for review
**Date**: 2026-04-15
**Relationship to v0.6**: additive; recommend bundling into v0.6 alongside
the workspace + PM workflow improvements
**Source**: gaps surfaced while executing the
`project-keel-ui-init` initial scoping with a PM agent

---

## 1. Context

### 1.1 The two gaps

While running `/pm-scope` on the keel-ui-init project (71 issues across
15 sessions, all in `planned`), two distinct gaps appeared at the
"now what?" moment after scoping completed.

**Gap A — no way to launch a planned session locally.** The v0.6 PM
command surface (per `2026-04-15-keel-workspace.md` §5.2) ships:

- `/pm-session-create` — create a session for an issue
- `/pm-session-launch` — transition `planned → queued`, write handoff
  comment, validate readiness
- `/pm-session-check` — readiness punch list
- `/pm-session-progress` — task-checklist rollup

`/pm-session-launch` per spec §6.3 transitions state to `queued` for an
external orchestrator (the future `keel-containers.md` runtime) to pick
up. **It does not spawn an executing agent.** Until the container
runtime ships, there is no codified path from "session is `planned`" to
"executing agent is actually running on it."

The PM agent and the human end up doing this by hand: "open a fresh
Claude Code session in the target repo, hand it the plan path, tell it
to cut a branch, follow the steps, open a PR." That procedural
complexity is the kind of thing a slash command is for.

**Gap B — no session-axis agenda view.** `keel agenda` groups issues
by status / executor / priority. There is no equivalent for sessions:
no "which sessions are launchable now," no "which are blocked on
which," no critical-path-by-session view. `keel session list` exists
but it's a flat alphabetical table — no interpretation.

A PM agent that has just finished scoping and wants to know "what
should we launch first" has to read all 15 session.yamls, build the
DAG in their head, and reason about it manually.

### 1.2 Why bundled

These are independent features, but bundling makes sense:

1. **Both surfaced in the same PM workflow (post-scoping launch).**
   Solving them together is what the workflow needs.
2. **Both fit the same v0.6 command-naming pattern** (entity-scoped
   `pm-session-*`).
3. **Shared readiness logic.** `pm-session-spawn`,
   `pm-session-launch`, `pm-session-check` all need the same gating
   checks; extracting that as a single `core/session_readiness.py`
   module avoids triplication.
4. **Both are small.** ~1 sprint each. Recommend folding into the v0.6
   release rather than waiting for v0.7.

### 1.3 Scope and non-goals

**In scope:**

- New CLI: `keel session spawn <session-id>` (the actual subprocess
  spawn + state transition)
- New slash command: `/pm-session-spawn <session-id>` (PM-side wrapper
  that adds handoff.yaml + comments + commit)
- New CLI: `keel session agenda` (or extend `keel agenda --by session`)
- New slash command: `/pm-session-agenda` (or extend `/pm-agenda` to
  accept `--by session`)
- Shared `core/session_readiness.py` extracted from existing
  `pm-session-launch` / `pm-session-check` logic
- `session.yaml.runtime_state` schema additions for spawn metadata

**Explicitly out of scope:**

- The container-based runtime that `pm-session-launch` queues for
  (covered by `docs/keel-containers.md`; separate effort)
- Auto-clone of target repos if not present (refuse with a clear
  fix_hint instead)
- Inter-session orchestration (auto-launching next session on
  completion) — that's a workflow concern, not a spawn concern
- Remote / cross-machine spawning (local only for v0.6)

---

## 2. Feature A — local session spawn

### 2.1 The mental model

`keel session spawn <id>` is the local-execution counterpart to
`keel session launch <id>` (the orchestrator-execution path). Same
readiness gate, same status transition semantics, different terminal:

```
                  ┌───────────────────────────────────────┐
                  │            session: planned           │
                  └─────────┬──────────────────┬──────────┘
                            │                  │
                  ┌─────────▼─────┐    ┌───────▼──────────┐
                  │ session launch│    │ session spawn    │
                  │ (orchestrator)│    │ (local CC)       │
                  └─────────┬─────┘    └───────┬──────────┘
                            │                  │
                  ┌─────────▼──────┐   ┌───────▼──────────┐
                  │ status: queued │   │ status: active   │
                  │ (waiting for   │   │ runtime_state.   │
                  │  orchestrator) │   │ claude_session_  │
                  └─────────┬──────┘   │ id populated     │
                            │          └───────┬──────────┘
                            │                  │
                            └─────► running ◄──┘
```

A session may move through `queued` then `active` (orchestrator path)
or directly `planned → active` (local-spawn path). Both terminate at
`completed` / `failed`.

### 2.2 CLI: `keel session spawn`

**Signature:**

```
keel session spawn <session-id>
  [--target-repo <slug>]       # if session has multiple repos, pick one
  [--log-dir <path>]           # override default ~/.keel/logs/
  [--max-turns N]              # claude -p --max-turns (default 200)
  [--allowed-tools T,T,T]      # claude -p --allowedTools (sensible default)
  [--append-system-prompt S]   # extra system prompt fragment
  [--dry-run]                  # print what would happen, don't spawn
  [--no-spawn]                 # do everything except the spawn (for tests)
  [--resume]                   # if session is already active, attach to existing
```

**Behaviour, in order:**

1. Load `session.yaml`. Verify status is `planned` (or `failed` if
   `--resume` and there's a previous spawn to retry).
2. Run `core.session_readiness.check(session_id)`. Same checks as
   `pm-session-launch`:
   - All `blocked_by_sessions` are in `completed` status
   - Required planning artifacts exist per `manifest.yaml`
   - `handoff.yaml` present and valid (per v0.6 §3.4)
   - Branch name in `handoff.yaml.branch` matches v0.6 convention
3. **Local-spawn-specific checks:**
   - Target repo (`session.yaml.repos[].repo`) has a registered local
     clone (`project.yaml.repos[<slug>].local` is set and exists).
     If multiple repos and no `--target-repo`, refuse and list options.
   - `claude` CLI is on `PATH` (verify via `which claude`).
   - Branch `handoff.yaml.branch` doesn't already exist in the target
     repo, OR `--resume` was passed.
4. Cut the branch in the target repo (`git -C <local> switch -c
   <branch> <base_branch>`).
5. Build the `claude -p` invocation (see §2.3 for the exact shape).
6. Spawn it backgrounded with `nohup ... &`. Capture PID.
7. Update `session.yaml`:
   - `status: planned → active`
   - `current_state: implementing` (per `enums/agent_state.yaml`)
   - `runtime_state.claude_session_id`: the spawned process PID for
     v0.6; future iteration captures the actual Claude session id from
     `--output-format json` first message
   - `runtime_state.workspace_volume`: the absolute path of the local
     repo clone (re-purpose existing field for "where the work
     happens")
   - Append to `engagements[]`:
     ```yaml
     - started_at: <iso8601>
       trigger: initial_launch
       claude_session_id: <pid>
       log_path: <log path>
     ```
8. Print a structured launch summary to stdout (table + log path).

**Exit codes:**

- `0` — spawn succeeded, session is `active`
- `2` — readiness check failed (printed reasons; nothing changed)
- `3` — local environment issue (missing clone, missing `claude` CLI;
  printed fix_hint; nothing changed)
- `4` — branch already exists and `--resume` not specified
- `5` — spawn launched but exited non-zero before backgrounding
  (shouldn't happen with `nohup &`; safety net)

### 2.3 The `claude -p` invocation

```bash
nohup claude -p "$(cat <plan-path>)

You are autonomous. Cut branch <branch> from <base_branch>.
Execute the plan above. Stop only at the plan's stop-and-ask points.
Open a PR titled '<type>(<session-slug>): <session-name>' when steps pass.
Report back as the final message." \
  --allowedTools "Bash,Read,Edit,Write,Glob,Grep" \
  --max-turns 200 \
  --output-format json \
  --append-system-prompt "session: <session-id>; project: <project-slug>" \
  > <log-path> 2>&1 &
```

**Key choices:**

- The plan content is **inlined** rather than passed as a path so the
  spawned session has the plan in context immediately, even if the
  caller's repo isn't accessible.
- `--allowedTools` defaults err on the safe side (read/write/grep/glob,
  plus Bash for git/uv/npm). No `WebFetch`, no `Agent` (we don't want
  spawned sessions spawning their own).
- `--output-format json` gives us a parseable session id we can capture
  from the first stdout line (post-v0.6 enhancement).
- `--max-turns 200` is generous for a typical 3–7 issue session.

**Log path:** `~/.keel/logs/<project-slug>/<session-id>-<timestamp>.log`.
Created on demand. Rotation is the user's problem (logrotate or
periodic cleanup); we don't manage it.

### 2.4 Slash command: `/pm-session-spawn`

```
---
name: pm-session-spawn
description: Launch a planned session locally by spawning a Claude Code subprocess.
argument-hint: "<session-id> [--target-repo <slug>]"
---

You are the project manager. Load the project-manager skill if not active.

1. Parse arguments. Validate session-id exists.
2. Run `keel session spawn <session-id> [flags] --no-spawn` to perform
   readiness checks + state writes WITHOUT spawning. Capture output.
3. If readiness fails: report to user, stop.
4. Write a launch comment on each contained issue (kind: status_change,
   body: "Session <id> launched locally; branch <branch>; log at <path>").
5. Run `keel validate --strict`.
6. Commit: "launch: <session-id> (local spawn)".
7. Re-run `keel session spawn <session-id> [flags]` (this time real)
   to do the actual subprocess spawn.
8. Report:
   - Session id, branch, log path, PID
   - `tail -f <log-path>` instructions
   - Estimated completion time (sum of plan step estimates)
```

**Why split the spawn into `--no-spawn` then real:** lets us commit a
clean state-transition commit BEFORE the long-running subprocess
starts. If the spawn fails, the commit was still meaningful (session
is `active`, not `planned`, awaiting a retry via `--resume`).

### 2.5 Schema additions

`session.yaml.runtime_state` (extends existing fields):

```yaml
runtime_state:
  claude_session_id: <string|null>     # PID for v0.6, real session-id post-v0.6
  langgraph_thread_id: null            # unchanged (future)
  workspace_volume: <abs-path|null>    # repurposed: local clone path for spawn
  log_path: <abs-path|null>            # NEW: where stdout/stderr stream
  spawn_kind: local|orchestrator|null  # NEW: which path was taken
```

`engagements[]` entries gain optional fields:

```yaml
- started_at: <iso8601>
  trigger: initial_launch | re_engagement | manual
  claude_session_id: <string>
  log_path: <abs-path>
  ended_at: <iso8601|null>
  outcome: <enum|null>
```

Validation:

- `runtime_state.claude_session_id` set ⇔ status in
  `{active, waiting_for_*, completed, failed, re_engaged}`
- `spawn_kind` required when `claude_session_id` is set

### 2.6 Resume + retry

`keel session spawn <id> --resume`:

- Permitted when status is `failed` or `active` (with stale PID; we
  poll `kill -0 <pid>` to detect dead sessions).
- Cuts no new branch (assumes branch exists from prior spawn).
- Spawns a new `claude -p` against the existing branch's worktree.
- Appends a new `engagements[]` entry with `trigger: re_engagement`.

### 2.7 Error cases

| Code | Trigger | Fix hint |
|---|---|---|
| `spawn/repo_not_cloned` | session repo has `local: null` in project.yaml | `git clone <ssh-url> <path> && keel project repo set <slug> --local <path>` |
| `spawn/claude_not_on_path` | `which claude` empty | "Install Claude Code or add to PATH." |
| `spawn/branch_exists` | branch already exists in target repo | Pass `--resume` to attach, or delete the branch |
| `spawn/multiple_repos_no_target` | session has 2+ repos and `--target-repo` not given | "Specify `--target-repo <slug>`. Repos: ..." |
| `spawn/blocked_by_incomplete` | one or more blocked_by_sessions not completed | "Wait for: <list>" |
| `spawn/handoff_invalid` | `handoff.yaml` missing or malformed | "Run `keel lint handoff <id>` for details." |
| `spawn/process_died_during_setup` | spawn exited before backgrounding | "Check log at <path>." |

---

## 3. Feature B — session-axis agenda

### 3.1 Output shape

Two equivalent invocations:

```
keel agenda --by session [--filter <expr>] [--format text|json]
keel session agenda      [--filter <expr>] [--format text|json]
```

Same data; `keel session agenda` is an alias for discoverability under
the `session` namespace.

**Text output (text format):**

```
keel-ui-init — 15 sessions
  ✓ 0 completed   ◐ 0 active   ◯ 13 planned   ⏸ 2 blocked

  critical path (by session): foundation-packaging → backend-server-scaffold →
    backend-read-services → backend-mutation-services → backend-routes →
    testing-backend (depth 6)

LAUNCHABLE NOW (no blockers):
  foundation-packaging      backend-coder    5 issues   feat/foundation-packaging
  frontend-scaffold         frontend-coder   7 issues   feat/frontend-scaffold

BLOCKED BY OTHERS:
  backend-server-scaffold   blocked_by: foundation-packaging
  backend-read-services     blocked_by: backend-server-scaffold
  backend-mutation-services blocked_by: backend-server-scaffold,
                                        backend-read-services
  ...

PARALLELISABLE ROUNDS (greedy):
  round 1: foundation-packaging | frontend-scaffold
  round 2: backend-server-scaffold | frontend-markdown
  round 3: backend-read-services | backend-realtime | backend-v2-stubs |
           frontend-views-core (after backend-routes)
  ...

RECOMMENDED NEXT (max 3, ranked by critical-path impact + parallel slack):
  1. /pm-session-spawn foundation-packaging   (unblocks 13)
  2. /pm-session-spawn frontend-scaffold      (unblocks 5, parallel to #1)
  3. (wait for #1 or #2 to unblock more)
```

**JSON output (json format):** structured per-session record + rounds
+ critical_path + recommendations. Schema in §3.4.

### 3.2 What it computes

For each session, the agenda interpreter derives:

- `is_launchable: bool` — status is `planned` AND all
  `blocked_by_sessions` are `completed`
- `is_blocked: bool` — has incomplete `blocked_by_sessions`
- `is_in_flight: bool` — status is `active | waiting_for_*`
- `is_stale: bool` — status `active` for > 3 days (lint-rule threshold,
  shared with `lint/session_stale`)
- `dependents: [session-id]` — sessions whose `blocked_by_sessions`
  contains this one
- `critical_path_position: int|null` — position on the longest path
  from any source to any sink
- `branch: string|null` — from `handoff.yaml.branch` if launched, else
  derived via `keel session derive-branch`

**Round computation:** topological sort with greedy levelling — round N
contains every session whose blocked_by sessions are all in rounds
< N. Pure derived value; not stored anywhere.

**Recommendation ranking:** primary key = "blast radius" (count of
sessions transitively unblocked); tiebreaker = "parallel slack" (does
launching this allow OTHER unblocked sessions to also launch in
parallel without dependency conflict).

### 3.3 Implementation surface

```
src/keel/core/session_agenda.py     # interpreter (DAG, rounds, recommendations)
src/keel/cli/agenda.py              # extend: --by session
src/keel/cli/session.py             # extend: agenda subcommand (alias)
src/keel/models/session_agenda.py   # output dataclasses (text + json shape)
```

Reuses:

- `keel.core.session_loader` (already exists in v0.5)
- `keel.core.session_readiness` (extracted in §2.1; see §4.1)

### 3.4 JSON output schema

```json
{
  "project": "keel-ui-init",
  "totals": { "completed": 0, "active": 0, "planned": 13, "blocked": 2 },
  "critical_path": ["foundation-packaging", "..."],
  "sessions": [
    {
      "id": "foundation-packaging",
      "name": "Foundation: packaging + module layout + CLI",
      "status": "planned",
      "agent": "backend-coder",
      "issues": ["KUI-2", "KUI-3", "KUI-4", "KUI-5", "KUI-6"],
      "blocked_by": [],
      "dependents": ["backend-server-scaffold"],
      "is_launchable": true,
      "is_blocked": false,
      "is_in_flight": false,
      "is_stale": false,
      "critical_path_position": 1,
      "branch": "feat/foundation-packaging",
      "log_path": null
    }
  ],
  "rounds": [
    ["foundation-packaging", "frontend-scaffold"],
    ["backend-server-scaffold", "frontend-markdown"]
  ],
  "recommendations": [
    {
      "session_id": "foundation-packaging",
      "rank": 1,
      "rationale": "On critical path; unblocks 13 sessions.",
      "command": "/pm-session-spawn foundation-packaging"
    }
  ]
}
```

### 3.5 Slash command: `/pm-session-agenda`

Optional convenience wrapper (single-page summary, max 300 words,
matches `/pm-agenda`'s style):

```
---
name: pm-session-agenda
description: Interpreted session-axis agenda with launch recommendations.
argument-hint: "[focus-area] [--format text|json]"
---

1. Run `keel session agenda --format json`.
2. Summarise:
   - Counts (active, blocked, launchable)
   - Critical path
   - Top 3 launch recommendations with rationale
   - Anything stale or unhealthy
3. Reference specific session ids.
4. End with the literal commands to run.
```

Existing `/pm-agenda` continues to default to issue-axis; passing
`--by session` switches it to session-axis. Discoverable both ways.

---

## 4. Shared infrastructure

### 4.1 `core/session_readiness.py`

Extracted from logic that already needs to exist for
`pm-session-launch` and `pm-session-check`. Single module so the three
related commands (launch, check, spawn) share one source of truth.

```python
# pseudo-API
def check(project_dir: Path, session_id: str, *, kind: Literal["launch", "spawn", "check"]) -> ReadinessReport:
    ...

@dataclass
class ReadinessReport:
    ready: bool
    must_fix: list[ReadinessIssue]
    warnings: list[ReadinessIssue]
    info: list[ReadinessIssue]
```

`kind="spawn"` adds local-environment checks (clone present, claude
on PATH); `kind="launch"` skips those.

### 4.2 Branch-existence check helper

`core.git_helpers.branch_exists(repo_path, branch_name) -> bool` —
small, used by spawn and useful elsewhere. Wraps `git -C <repo>
rev-parse --verify <branch>`.

### 4.3 Process-alive check

`core.process_helpers.is_alive(pid: int) -> bool` — `os.kill(pid,
0)` wrapped to return bool. Used by `--resume` to detect dead spawned
sessions.

---

## 5. Coexistence + naming with v0.6

### 5.1 Final command surface (post-addendum)

Adding to v0.6 §5.2:

**Entity-scoped (8, +1):**

| Command | Purpose |
|---|---|
| `pm-issue-close` | (existing) |
| `pm-session-create` | (existing) |
| `pm-session-launch` | Transition to `queued` for orchestrator pickup |
| **`pm-session-spawn`** | **NEW**: transition to `active` and spawn local Claude CC |
| `pm-session-check` | (existing) |
| `pm-session-progress` | (existing) |
| `pm-project-create` | (existing) |
| `pm-project-sync` | (existing) |

**Interpretive (4, +1):**

`pm-status`, `pm-agenda`, `pm-graph`, **`pm-session-agenda`** (NEW)

OR: extend `pm-agenda` with `--by session` and skip the explicit
`pm-session-agenda` command. Recommendation: ship both — the explicit
form is more discoverable when you know you want session view, the
flag form lets users compose with other agenda flags.

### 5.2 Status enum impact

No new statuses. Existing enum (`planned, active, waiting_for_ci,
waiting_for_review, waiting_for_deploy, re_engaged, completed,
failed`) suffices. The `queued` value referenced in v0.6 §6.3 may
need adding if not already present — verify against
`enums/session_status.yaml`.

### 5.3 Differences spawn vs launch

| | `pm-session-launch` | `pm-session-spawn` |
|---|---|---|
| Terminal status | `queued` | `active` |
| Spawns process? | No | Yes |
| Requires local clone? | No | Yes |
| Requires `claude` CLI? | No | Yes |
| Pickup mechanism | Orchestrator polls `queued` | This command spawns directly |
| Ready in v0.6? | Yes (orchestrator may not be) | Yes |

Both are valid; choice depends on whether the orchestrator runtime
is available. In v0.6 the orchestrator may not yet exist in usable
form, so `spawn` is the practical path.

---

## 6. Migration + backward compat

- Both features are purely additive. Existing v0.5 / draft v0.6
  projects continue to function unchanged.
- No data migration required. New `runtime_state.log_path` and
  `spawn_kind` fields are optional.
- `keel agenda` without `--by` defaults to existing issue-axis
  behaviour.

---

## 7. Testing

### 7.1 Unit tests

| Module | Tests |
|---|---|
| `core/session_readiness.py` | 12 (per check kind, per failure mode) |
| `core/session_agenda.py` | 10 (DAG correctness, rounds, recommendations, single-session edge cases) |
| `core/git_helpers.py::branch_exists` | 4 |
| `core/process_helpers.py::is_alive` | 3 |
| `cli/session.py::spawn` | 8 (each error code path) |
| `cli/session.py::agenda` | 4 (text + json + filter) |

### 7.2 Integration tests

- `test_session_spawn_happy.py` — fixture project with a fixture repo
  + a fake `claude` shim that sleeps 2 seconds and exits 0; assert
  state transitions, log file, branch creation, runtime_state fields
- `test_session_spawn_blocked.py` — assert refuses with exit 2 when
  blocked_by incomplete
- `test_session_spawn_no_clone.py` — exit 3 with clear hint
- `test_session_spawn_branch_exists.py` — exit 4; `--resume` works
- `test_session_spawn_resume_after_failure.py` — second engagement
  appended, prior preserved
- `test_session_agenda_dag.py` — synthesised 10-session DAG,
  assert round structure, critical path, recommendations
- `test_session_agenda_single_session.py` — degenerate case
- `test_session_agenda_cycle.py` — refuses with clear error (cycle
  in blocked_by_sessions)

### 7.3 Slash command tests

- `test_pm_session_spawn_frontmatter.py` — valid command-doc shape
- `test_pm_session_agenda_output.py` — fixture project, assert summary
  contains expected session ids

### 7.4 Coverage gates

- All new error codes: ≥1 passing + ≥1 failing fixture
- The `claude` subprocess is always replaced with a shim in tests
  (never spawn a real Claude session in CI)
- Test count growth: ~50 new tests

---

## 8. Open questions

None blocking. To resolve during implementation:

- **Spawn log location.** `~/.keel/logs/<project>/<session>-<ts>.log`
  vs `<project>/.keel/logs/<session>-<ts>.log`. Lean: home-level so
  logs survive project moves; user can override with `--log-dir`.
- **`runtime_state.claude_session_id` value for v0.6.** PID is easy
  but doesn't survive process death; the parsed session id from
  Claude's `--output-format json` first message is more robust but
  requires us to read the first line of the log before backgrounding
  fully. Lean: PID for v0.6, parsed id in a follow-up.
- **`/pm-session-spawn` after `keel session spawn`: should the slash
  command also tail the log into the calling terminal as a final
  step?** Lean: no by default (hangs the slash command), yes with
  `--watch` flag.
- **Round display when project has > 8 sessions per round** (won't
  happen for keel-ui-init but could for big projects). Lean: cap
  at 6 per line in text output, full data in json.

---

## 9. Cross-references

- `docs/specs/2026-04-15-keel-workspace.md` —
  parent v0.6 spec; this addendum extends §4.4 (Missing CLI commands)
  and §5 (PM command surface)
- `docs/keel-containers.md` — orchestrator runtime; long-term home
  for the `pm-session-launch → queued → orchestrator pickup` path
- `docs/keel-ui.md` — UI surface that will eventually visualise
  `keel session agenda` output
- `enums/session_status.yaml` — verify `queued` exists; add if not

---

## 10. Effort estimate

| Component | Estimate |
|---|---|
| `core/session_readiness.py` (extract + extend) | 1 day |
| `core/session_agenda.py` | 1.5 days |
| `core/git_helpers.py`, `core/process_helpers.py` | 0.5 day |
| `cli/session.py::spawn` | 1.5 days |
| `cli/session.py::agenda`, `cli/agenda.py::--by session` | 0.5 day |
| Schema additions + validation rules | 0.5 day |
| Slash command files (`pm-session-spawn`, `pm-session-agenda`) | 0.5 day |
| Tests (unit + integration + slash) | 2 days |
| Docs updates (workspace spec, README, skill references) | 0.5 day |
| **Total** | **~8.5 days** |

Recommend bundling into v0.6 release rather than slipping to v0.7 —
the workflow gap is real today and the surface area is small.
