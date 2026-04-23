# v0.7.2 Subprocess — Follow-up Plan

> Follow-up to PR #16 (`feat/v0.7.2-tmux`). Fixes bugs surfaced during
> self-review + closes the two deferred items (real-claude smoke,
> stream-json prettifier).

## Context

PR #16 landed the `SubprocessRuntime` + resume flow + headless
stop-and-ask. Self-review surfaced eleven issues:

- **5 bugs** (`project_slug` in log path, CLAUDE.md backup
  accumulation, manual attach doesn't honour resume state, test gap,
  stale spec reference)
- **6 design gaps** (log accumulation, no real-claude smoke, process
  group handling, pause doesn't wait, CLAUDE.md re-render on resume,
  `project_slug` threading)
- Plus the two explicitly-deferred items.

This plan groups them into seven commits against a new branch
`fix/v0.7.2-subprocess-followups`. No new runtime modes; no schema
changes that require migration. Purely corrective + one new
read-only subcommand (`tripwire session log`) and one new script.

## Approach

### H1 — fix `project_slug` in log path (bugs #1, #11)

- `src/tripwire/runtimes/base.py` `PreppedSession`: add
  `project_slug: str` field (required).
- `src/tripwire/runtimes/prep.py` `run()`: populate `project_slug`
  into the returned `PreppedSession` using the same
  `_load_project_slug` helper already used for `system_append`.
- `src/tripwire/runtimes/subprocess.py` `_render_log_path`: read from
  `prepped.project_slug` directly; drop the `getattr(..., "unknown")`
  fallback.
- `tests/unit/test_runtimes_subprocess.py::test_start_invokes_popen_with_expected_argv`:
  assert the log_path string contains the expected project slug
  segment (not just that its parent exists). Adds one line; prevents
  regression.
- `tests/unit/test_runtimes_prep.py::TestPrepRun`: assert
  `prepped.project_slug` matches the project name slug.

### H2 — idempotent CLAUDE.md render (bug #2, gap #10)

Apply the F4 pattern to CLAUDE.md:

- `render_claude_md` writes a sentinel file next to CLAUDE.md whose
  content is a hash of (agent_id, skill_names, worktree paths,
  session_id, template version).
- If the sentinel matches the wanted hash AND CLAUDE.md exists: no-op.
- Otherwise: back-up-then-rewrite as today, then write the new
  sentinel.
- Tests: `test_claude_md_idempotent_when_unchanged`, paired with
  `test_claude_md_backed_up_on_change`. Same shape as the existing
  skills tests.

### H3 — manual runtime honours resume state in attach (bug #3)

- `src/tripwire/models/session.py` `RuntimeState`: add
  `last_spawn_resumed: bool = False`.
- `src/tripwire/cli/session.py` `session_spawn_cmd`: set
  `session.runtime_state.last_spawn_resumed = resume_flag` when
  writing back the start result.
- `src/tripwire/runtimes/manual.py` `attach_command`: if
  `session.runtime_state.last_spawn_resumed`, render the command with
  `--resume` in place of `--session-id`.
- `tests/unit/test_runtimes_manual.py`: new test
  `test_attach_command_honours_resume_state`.

### H4 — `SubprocessRuntime.pause` waits for the process (gap #9)

- `src/tripwire/runtimes/subprocess.py` `pause`: after SIGTERM, poll
  `is_alive` at 100ms intervals up to 2s. If still alive, return
  without escalating — pause means "stop for now"; escalation to
  SIGKILL belongs to `abandon`. If exited, return cleanly.
- Adjust `session_pause_cmd` so status transitions only happen after
  `pause` returns: if the process is still alive at the 2s deadline,
  surface a warning and leave status as `executing`. If exited: set
  `paused`. Status no longer diverges from reality.
- Test: `test_pause_waits_for_exit`, `test_pause_warns_when_sigterm_ignored`.

### H5 — log retention + `tripwire session logs` subcommand (gap #6)

- `src/tripwire/cli/session.py`: new `session logs <id>` subcommand.
  Lists all log files for a session (e.g. multiple spawn attempts),
  `tail -n` mode by default, `--full` for full dump.
- `session cleanup`: optional `--with-logs` flag to also prune the
  session's logs when the session is completed/abandoned.
- Test: `tests/unit/test_session_logs_cli.py`.

### H6 — `tripwire session summary <id>` — stream-json prettifier (deferred #13)

Parse the latest log file's stream-json events and extract:

- Session id, claude session uuid, runtime, start / end timestamps.
- Final assistant text (last text block).
- Exit subtype (`success` / `error_max_turns` / `error_rate_limit`).
- Tool call count, token usage from the final `result` event.
- Question detection heuristic: if the final assistant text contains
  a "?" and exit subtype is `success`, flag as "stopped to ask."

Output text/json format.

- `src/tripwire/cli/session.py::session_summary_cmd`.
- `src/tripwire/core/session_log_parser.py` — pure function consuming
  a stream-json file and returning a `SessionLogSummary` dataclass.
- `tests/unit/test_session_log_parser.py` with golden stream-json
  fixtures covering happy path, error_max_turns, stop-and-ask pattern.

### H7 — real-claude smoke script + spec note (deferred #12, bug #5, gap #8)

- `scripts/smoke-subprocess-runtime.sh` — standalone bash script:
  - Creates a throwaway tripwire project in `$(mktemp -d)`.
  - Registers the same throwaway dir as its own repo.
  - Authors a trivial session.yaml + agents/backend-coder.yaml +
    plan.md (e.g. "Create a file called hello.txt containing 'hi'.
    Commit and push it.").
  - Runs `tripwire session queue` + `tripwire session spawn`.
  - Waits for process exit (up to `$TW_SMOKE_TIMEOUT`, default 120s).
  - Asserts: file hello.txt created, git log shows commit, session
    status transitioned.
  - Runs `tripwire session abandon` for defensive cleanup.
  - Exits 0 if happy path; prints log file location on error.
- `scripts/smoke-subprocess-resume.sh` — variant that forces
  stop-and-ask (plan.md asks an unanswerable question), then adds
  `## PM follow-up` and runs `spawn --resume`, verifies the agent
  continues with prior context.
- `docs/superpowers/specs/2026-04-22-session-execution-modes.md`:
  correct the stale "Retained from the design" bullet in the first
  correction preamble (`RuntimeState.tmux_session_name` was since
  removed).
- Document process-group handling (gap #8) as a known-limitation
  note in the spec: SIGTERM to the pid reaches only claude itself,
  not children. Empirically non-issue for current claude but flagged
  for future.

## Critical files

| File | Change |
|---|---|
| `src/tripwire/runtimes/base.py` | Add `PreppedSession.project_slug`. |
| `src/tripwire/runtimes/prep.py` | Populate `project_slug`; idempotent CLAUDE.md. |
| `src/tripwire/runtimes/subprocess.py` | Read `project_slug`; pause waits. |
| `src/tripwire/runtimes/manual.py` | Honour resume state in attach. |
| `src/tripwire/models/session.py` | `RuntimeState.last_spawn_resumed`. |
| `src/tripwire/cli/session.py` | `session logs` + `session summary` subcommands; pause-waits rewire. |
| `src/tripwire/core/session_log_parser.py` | **NEW** — stream-json → SessionLogSummary. |
| `scripts/smoke-subprocess-runtime.sh` | **NEW** — end-to-end happy path. |
| `scripts/smoke-subprocess-resume.sh` | **NEW** — end-to-end resume path. |
| `docs/superpowers/specs/2026-04-22-session-execution-modes.md` | Stale-reference + process-group notes. |
| Tests | Added across the touched areas; no deletes. |

## Verification

1. `uv run python -m pytest tests/ -q` — 1335+ passing (add ~8 new
   tests from H1–H6), 0 skipped.
2. `uv run ruff check` — clean.
3. `bash scripts/smoke-subprocess-runtime.sh` — passes against a
   real-claude-installed host.
4. `bash scripts/smoke-subprocess-resume.sh` — passes; agent picks
   up prior context after `--resume`.
5. `grep -rn "unknown" ~/.tripwire/logs/ 2>/dev/null` — no more
   `unknown` directory appearing in fresh log paths (H1).
6. Run `tripwire session spawn` twice on the same session
   (initial → pause → resume); confirm only **one** `CLAUDE.md.bak.*`
   file ever exists, regardless of how many times resume is called
   against an unchanged agent+skill set (H2).

## Scope — explicitly out

- **No runtime-level changes** beyond the targeted bugs. `manual` and
  `subprocess` are the two runtimes; container mode stays future.
- **No schema migration.** `last_spawn_resumed` defaults to False for
  existing sessions; CLAUDE.md sentinel is additive.
- **No changes to `session complete` / PR flow.** That's the previous
  correction's territory.
- **Pretty-print as a standalone binary.** H6 lives as a subcommand,
  not a new tool.

## Rollback

Each commit is self-contained and revertable. H1 is the most
entangled (touches three files); H7 is purely additive (scripts + a
spec note). If a bug resurfaces, individual commit reverts restore
the prior behaviour.
