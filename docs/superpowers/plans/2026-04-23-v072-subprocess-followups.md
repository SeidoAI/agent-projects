# v0.7.2 subprocess — follow-up plan

> Follow-up to PR #16 (`feat/v0.7.2-tmux`). Fixes bugs surfaced during
> self-review, closes two deferred items, sweeps stale tmux residue,
> and refreshes the PR body to match the pivoted scope.

## Context

PR #16 landed `SubprocessRuntime` + resume flow + headless stop-and-
ask, but self-review surfaced **five bugs** (`project_slug` not
threaded into `PreppedSession`; CLAUDE.md backups accumulate on every
resume; manual runtime's attach ignores resume state; test-assertion
gaps; stale spec reference), **six design gaps** (log accumulation,
no real-claude smoke, process-group handling, pause doesn't wait,
CLAUDE.md re-render on resume, `project_slug` threading), and the
**two explicitly-deferred items** from the pivot plan (real-claude
smoke script, stream-json prettifier).

A grep pass over `src/` also shows that after ripping `TmuxRuntime`,
several module docstrings and inline comments still reference tmux —
harmless hanging text, but a reader would plausibly be confused.

All of this groups into nine self-contained phases. No new runtime
modes; no schema changes that need migration. Corrective work plus
one new subcommand (`tripwire session logs`), one new read-only
subcommand (`tripwire session summary`), two smoke scripts, and a
mechanical tmux-residue sweep.

## What the tests should have caught (and didn't)

Before the plan itself, an honest accounting — because the same
testing blind spots will let the next round of bugs through too if
the new tests just repeat them.

### Bug 1: `project_slug` missing on `PreppedSession`

- **Code smell that should have been noticed:**
  `subprocess.py:39` reads `getattr(prepped, "project_slug", None)
  or "unknown"`. `PreppedSession` is a typed dataclass — using
  `getattr` with a default against a struct you control is always a
  red flag. Either the field exists (attribute access) or it
  doesn't (fix the struct). The `"unknown"` literal is the ghost
  of a field that was never added. Every log lands in
  `~/.tripwire/logs/unknown/`.
- **Why the test didn't catch it:**
  `test_start_invokes_popen_with_expected_argv` uses a test-only
  template `str(tmp_path / "logs" / "{session_id}.log")` — **no
  `{project_slug}` token**. So even if the runtime produced
  `"unknown"`, it wouldn't appear in the rendered path. The test
  assertion `assert log_path.parent.exists()` is always true
  because `_render_log_path` calls `mkdir(parents=True,
  exist_ok=True)` unconditionally.
- **Pattern the new tests adopt (H1):**
  1. Use a template that exercises `{project_slug}` — the same
     shape as the production default.
  2. Assert the rendered path **contains the expected project
     slug** and **does not contain `"unknown"`**. Semantic content
     assertions, not "the side effect happened" assertions.
  3. Make `PreppedSession.project_slug` a required field (no
     default). Missing-field bugs then raise `TypeError` at
     dataclass construction, not silent `AttributeError`-shaped
     default-fallback at read.

### Bug 2: CLAUDE.md backups accumulate on every resume

- **Why the test didn't catch it:**
  There's no test that calls `render_claude_md` twice on the same
  worktree and counts the backup files. The existing
  `test_existing_claude_md_backed_up` asserts exactly one backup
  after one call — but doesn't probe the second call, which is
  exactly when the accumulation happens.
- **Pattern the new tests adopt (H2):** mirror the F4 skills-
  idempotency tests — `test_unchanged_skill_set_does_not_back_up`
  exists for skills; the equivalent for CLAUDE.md does not. H2
  adds it. Idempotency testing is "call the thing three times,
  assert the world still looks like one call."

### Bug 5: stale tmux residue in docstrings + comments

- **What would have caught it:**
  `grep -rn 'tmux\|Tmux\|TMUX' src/` run once before commit. A
  thirty-second mechanical check that I didn't do. H8 runs exactly
  that sweep now — no permanent regression test, because this
  class of residue is more reliably caught by "grep before push"
  habit than by a test that fires on every CI run forever.

### General pattern

The common shape of "test passed, bug shipped" in this PR was:

> The test asserted **that a thing happened** (a file got created,
> a function ran, an argument appeared in argv) rather than **what
> the thing's content was** (was the filename composed of the right
> parts, was the argument's value right, was the output shape
> correct).

Every test authored or touched in H1–H7 below uses **content
assertions** where applicable. Where only a side effect can be
checked, the test also checks the effect's *shape*.

## Approach

### H1 — thread `project_slug` into `PreppedSession` (bugs #1, #11)

Root-cause fix for `getattr(..., "unknown")`. The value is already
computed during prep (`_load_project_slug`), just not attached to
the output.

**Code**
- `src/tripwire/runtimes/base.py` `PreppedSession`: add
  `project_slug: str` (required — no default).
- `src/tripwire/runtimes/prep.py` `run()`: populate
  `project_slug=proj_slug` in the `PreppedSession` constructor
  (the value is already computed for `system_append`; just thread
  it through).
- `src/tripwire/runtimes/subprocess.py` `_render_log_path`: read
  `prepped.project_slug` directly. **Delete** the
  `getattr(..., None) or "unknown"` line.

**Tests**
- `tests/unit/test_runtimes_subprocess.py::_prepped` helper:
  template becomes
  `str(tmp_path / "logs" / "{project_slug}" / "{session_id}.log")` —
  the same interpolation shape as the shipped default. Add
  `project_slug="test-proj"` to the `PreppedSession` kwargs.
- `tests/unit/test_runtimes_subprocess.py::test_start_invokes_popen_with_expected_argv`:
  **new assertions** — `assert "test-proj" in str(result.log_path)`,
  `assert "unknown" not in str(result.log_path)`.
- `tests/unit/test_runtimes_prep.py::TestPrepRun::test_end_to_end`:
  **new assertion** — `assert prepped.project_slug` is non-empty
  and matches the slug of the test project.

### H2 — idempotent CLAUDE.md render (bug #2, gap #10)

Apply the F4 skills-sentinel pattern to CLAUDE.md.

**Code**
- `src/tripwire/runtimes/prep.py` `render_claude_md`: write a
  sentinel file `<code_worktree>/.claude/.tripwire-claude-md-hash`
  whose content is a SHA256 of `(agent_id, sorted(skill_names),
  worktree repo/path tuples, session_id, template version)`.
  Template version = a module-level `_CLAUDE_MD_TEMPLATE_VERSION`
  constant bumped manually when the Jinja template shape changes.
- If CLAUDE.md exists AND sentinel matches the wanted hash: no-op.
- Otherwise: back up existing CLAUDE.md as today, then rewrite,
  then write the new sentinel.

**Tests** (mirror `TestCopySkillsIdempotency` shape exactly)
- `test_claude_md_idempotent_when_unchanged`: call render three
  times with identical inputs; assert zero `CLAUDE.md.bak.*` files.
- `test_claude_md_backed_up_on_change`: call render, mutate
  `skill_names`, call again; assert exactly one backup.
- `test_claude_md_backed_up_on_template_version_bump`: same shape
  but mutate the template version constant; assert exactly one
  backup.

### H3 — manual runtime's attach honours resume state (bug #3)

Today `ManualRuntime.attach_command` always calls
`_start_command(..., resume=False)` because the runtime has no way
of knowing whether the last spawn was resume or fresh.

**Code**
- `src/tripwire/models/session.py` `RuntimeState`: add
  `last_spawn_resumed: bool = False`.
- `src/tripwire/cli/session.py` `session_spawn_cmd`: set
  `session.runtime_state.last_spawn_resumed = resume_flag` when
  writing the start result back.
- `src/tripwire/runtimes/manual.py` `attach_command`: pass
  `resume=session.runtime_state.last_spawn_resumed` into
  `_start_command`.

**Tests**
- `tests/unit/test_runtimes_manual.py::test_attach_command_honours_resume_state`:
  two sessions, one with `last_spawn_resumed=True`, one False;
  assert the printed command has `--resume` in one and not the
  other.

### H4 — `SubprocessRuntime.pause` waits for actual exit (gap #9)

Today `pause` sends SIGTERM and returns immediately; the CLI layer
then flips status to `paused` even though the process may still be
running. Status can diverge from reality for seconds.

**Code**
- `src/tripwire/runtimes/subprocess.py` `pause`: after SIGTERM,
  poll `is_alive` at 100ms intervals up to 2s. If exited within
  window, return normally. If still alive at deadline, raise
  `RuntimeError("SIGTERM not honoured within 2s — escalate via
  'tripwire session abandon'")`. Pause means "stop for now";
  escalation to SIGKILL is abandon's job.
- `src/tripwire/cli/session.py` `session_pause_cmd`: wrap the
  `runtime.pause(session)` call in try/except `RuntimeError`. On
  error, surface a warning and **leave status as `executing`** —
  state matches reality. On success, set status to `paused`.

**Tests**
- `tests/unit/test_runtimes_subprocess.py::test_pause_waits_for_exit`:
  `is_alive` returns True once, then False; `pause` returns
  normally; assert the polling loop ran at least once (mock
  `time.sleep` to inspect call count).
- `test_pause_raises_when_sigterm_ignored`: `is_alive` returns
  True throughout; assert `RuntimeError` is raised (monkeypatch
  `time.monotonic` to skip the real 2s wall time).

### H5 — `tripwire session logs <id>` subcommand + cleanup flag (gap #6)

Per-spawn logs accumulate (each spawn writes a new
`{session_id}-{timestamp}.log`). Today there's no way to view or
prune them short of manual filesystem walking.

**Code**
- `src/tripwire/cli/session.py` new `session_logs_cmd`:
  - Lists all log files under the session's log directory
    (resolve via the log_path_template's parent).
  - `--tail N` (default: last 50 lines of the latest log).
  - `--full` dumps the entire latest log.
  - `--list` just lists files with sizes + mtimes, doesn't dump.
- `src/tripwire/cli/session.py` `session_cleanup_cmd`: add
  `--with-logs` flag — when the session is completed/abandoned
  AND `--with-logs`, also `rm -rf` the session's log directory
  after worktree teardown.

**Tests** — `tests/unit/test_session_logs_cli.py`:
- `test_logs_lists_multiple_files`: seed two log files, run
  `session logs <id> --list`; assert both appear in output.
- `test_logs_tail_default`: seed a log with 100 lines; assert
  output contains only the last 50.
- `test_logs_full_dumps_everything`: assert `--full` prints all
  lines.
- `test_cleanup_with_logs_removes_log_dir`: assert log dir is
  gone after `cleanup --with-logs`; not gone without.

### H6 — `tripwire session summary <id>` (deferred #13, stream-json prettifier)

Parse the latest log file's stream-json events into a human-readable
summary.

**Code**
- New `src/tripwire/core/session_log_parser.py`:
  - `@dataclass SessionLogSummary`: session_id, claude_session_id,
    runtime_name, started_at, ended_at, final_text, exit_subtype,
    tool_call_count, token_usage, stopped_to_ask: bool.
  - `parse(log_path: Path) -> SessionLogSummary` — pure function.
    Reads stream-json line by line; tracks the last assistant
    text block, counts `tool_use` events, extracts the terminal
    `result` event for token usage + exit subtype. Sets
    `stopped_to_ask = True` when `exit_subtype == "success"` and
    `final_text` contains a question-shaped sentence.
- `src/tripwire/cli/session.py` new `session_summary_cmd`:
  - `--format text|json` (default text).
  - Text format: human summary with the final assistant text
    quoted + exit diagnosis + "stopped to ask" flag if set.
  - JSON format: dump the dataclass.

**Tests** — `tests/unit/test_session_log_parser.py` golden-file:
- `fixtures/stream-json/happy_path.log` (success, PR opened).
- `fixtures/stream-json/error_max_turns.log`.
- `fixtures/stream-json/stop_and_ask.log` (success exit, final
  text ending with "?").
- Each test parses its fixture and asserts the **full** dataclass
  shape — not just "a summary was produced."

### H7 — real-claude smoke scripts + spec fixes (deferred #12, bug #5, gap #8)

**Scripts**
- `scripts/smoke-subprocess-runtime.sh`:
  1. `mktemp -d` → throwaway project root.
  2. `tripwire init` against it; author minimal `session.yaml`,
     `agents/backend-coder.yaml`, `plan.md` (task: "Create
     `hello.txt` with content `hi`. Commit and push.").
  3. `tripwire session queue` + `tripwire session spawn`.
  4. Poll for process exit (up to `$TW_SMOKE_TIMEOUT`, default
     120s).
  5. Assert: `hello.txt` exists in the worktree, `git log` shows
     the commit, session status transitioned.
  6. `tripwire session abandon` for defensive cleanup.
  7. Exit 0 on happy path; print the session log path on error.
- `scripts/smoke-subprocess-resume.sh`:
  1. Same setup but plan.md asks an unanswerable question.
  2. Spawn; wait for exit-with-question.
  3. Append `## PM follow-up\n<answer>` to plan.md.
  4. `tripwire session spawn <id> --resume`.
  5. Poll; assert the agent's log references the follow-up text
     (proves it re-read the updated plan).

**Spec + plan fixes**
- `docs/specs/2026-04-22-session-execution-modes.md`:
  - In the first "Correction (2026-04-22 afternoon)" preamble,
    remove the stale bullet that still lists
    `RuntimeState.tmux_session_name` under "Retained from the
    design" (it was removed in G1).
  - Add a **known-limitation note**: SIGTERM to the claude pid
    reaches only the claude process itself. If claude ever spawns
    children that install their own SIGTERM handlers or detach,
    those children outlive the pause/abandon call. Empirically
    non-issue for claude 2.1.x but flagged. Mitigation:
    `start_new_session=True` is already passed to `Popen`, so
    `os.killpg(pid, SIGTERM)` is a one-line upgrade when it
    matters.

### H8 — mechanical tmux-residue sweep (reader-hygiene)

A thirty-second grep-and-edit pass that should have been the last
thing before pushing PR #16. Findings from running
`grep -rn 'tmux\|Tmux\|TMUX' src/`:

| File:line | Current text | Fix |
|---|---|---|
| `src/tripwire/runtimes/base.py:3` | "Each runtime implementation (tmux, manual, future: container)" | "Each runtime implementation (subprocess, manual, future: container)" |
| `src/tripwire/runtimes/base.py:73` | "e.g. tmux missing" | "e.g. a required binary missing" |
| `src/tripwire/runtimes/prep.py:280` | "what the tmux send-keys step delivers on ready-probe timeout" | "and what the subprocess runtime passes to `claude -p` on start" |
| `src/tripwire/runtimes/subprocess.py:10` | "tmux-based runtimes suffer from" | "an interactive runtime would need to solve" |
| `src/tripwire/cli/session.py:515-516` | "tmux runtimes exec \`tmux attach\`; manual runtimes print the command" | "subprocess runtimes exec \`tail -f <log>\`; manual runtimes print the command" |
| `src/tripwire/cli/session.py:685` | "# If the runtime still has a live process (tmux session, etc.)," | "# If the runtime still has a live process (claude subprocess, etc.)," |
| `src/tripwire/runtimes/manual.py:3` | "Does the skill copy + CLAUDE.md render like tmux" | "Does the skill copy + CLAUDE.md render like the subprocess runtime" |
| `tests/unit/test_runtimes_registry.py:26-28` | `AttachExec(argv=["tmux", "attach"])` test data | `AttachExec(argv=["tail", "-f", "/tmp/x.log"])` — matches real subprocess attach shape |

**No permanent regression test.** Per-PR residue of this kind is
better caught by a "grep before push" habit than by a test that
runs every CI cycle forever. Positive assertions in tests
(`get_runtime("tmux")` raises, `invocation.runtime == "tmux"`
rejected) stay — those are correctness guards, not residue.

**Spec files** (under `docs/`) are explicitly exempt: historical
design docs naturally reference tmux, and rewriting history is
anti-goal. The spec's correction preambles already frame tmux as
the reverted path.

### H9 — PR #16 body refresh

PR #16's current body still describes the tmux-era scope ("Ships
`TmuxRuntime`", "live-attach inside `tmux new-session -d`", "tmux-
gated integration", "v0.7 compat for pid-only runtime_state"). The
title is already correct ("feat(v0.7.2): SubprocessRuntime + resume
flow + headless stop-and-ask").

**New body shape** (applied post-approval via `gh pr edit`):

- Summary bullets:
  - `SubprocessRuntime` — default runtime; `claude -p` via Popen
    with stream-json → log file; `tripwire session attach <id>`
    resolves to `tail -f <log>`.
  - `ManualRuntime` — prep-only escape hatch; prints the
    invocation and exits.
  - **Resume flow** — short continuation prompt template (claude's
    own jsonl carries history); `--resume <uuid>` not
    `--session-id` on resume; prep reuses existing worktrees on
    resume; `.tripwire/kickoff.md` rewritten each spawn.
  - **Headless stop-and-ask** — `AskUserQuestion` +
    `SendUserMessage` disallowed; prompt instructs the agent to
    write questions as text and exit 0.
  - **Runtime-agnostic prep pipeline** — worktrees per
    `session.repos`, skills copy with idempotency sentinel,
    CLAUDE.md render, kickoff.md write.
  - Drops the tmux path (trust gate + newline quirks + ready-
    marker fragility + hard dep). History traced in the spec's
    second correction preamble.
- Link the original spec + both correction preambles + this
  follow-up plan.
- Test plan: 1337 passing, 0 skipped on this host. Follow-up work
  from this plan lands on the same branch before merge.
- Note: follow-ups (H1–H8) land as additional commits on this same
  branch pre-merge, not a second PR.

## Branch strategy

All nine phases land on **`feat/v0.7.2-tmux`** (the existing PR #16
branch). The PR title is already correct for the pivoted scope.
Each phase is one commit — nine commits on top of `27bc3fb`. No new
branch; no rebase. Reviewers who already saw the subprocess pivot
see only the delta.

Justification for not creating a `fix/v0.7.2-subprocess-followups`
branch: the work is strictly corrective + deferred items the PR
explicitly promised, and the PR hasn't merged yet. Piling follow-up
commits onto the open PR keeps the unit of review a single "v0.7.2
ships" decision rather than splitting it.

## Critical files

| File | Change |
|---|---|
| `src/tripwire/runtimes/base.py` | Add `PreppedSession.project_slug`; docstring sweep (H1, H8). |
| `src/tripwire/runtimes/prep.py` | Populate `project_slug`; CLAUDE.md sentinel; docstring sweep (H1, H2, H8). |
| `src/tripwire/runtimes/subprocess.py` | Read `project_slug`; pause waits; docstring sweep (H1, H4, H8). |
| `src/tripwire/runtimes/manual.py` | Honour resume state in attach; docstring sweep (H3, H8). |
| `src/tripwire/models/session.py` | `RuntimeState.last_spawn_resumed` (H3). |
| `src/tripwire/cli/session.py` | `session logs`, `session summary`; pause-waits rewire; docstring sweep (H4, H5, H6, H8). |
| `src/tripwire/core/session_log_parser.py` | **NEW** (H6). |
| `tests/unit/test_runtimes_subprocess.py` | Project-slug content assertions; pause-wait tests (H1, H4). |
| `tests/unit/test_runtimes_prep.py` | CLAUDE.md idempotency tests (H2). |
| `tests/unit/test_runtimes_manual.py` | Resume-state attach test (H3). |
| `tests/unit/test_session_logs_cli.py` | **NEW** (H5). |
| `tests/unit/test_session_log_parser.py` | **NEW** + stream-json fixtures (H6). |
| `scripts/smoke-subprocess-runtime.sh` | **NEW** (H7). |
| `scripts/smoke-subprocess-resume.sh` | **NEW** (H7). |
| `docs/specs/2026-04-22-session-execution-modes.md` | Stale-bullet fix + process-group note (H7). |
| PR #16 body | Rewrite to match pivot (H9). |

## Verification

1. `uv run python -m pytest tests/ -q` — 1337 + ~12 new tests
   passing, 0 skipped.
2. `uv run ruff check` — clean.
3. `grep -rn 'tmux\|Tmux\|TMUX' src/` — zero hits after H8.
4. Spawn a session on a host with claude installed; verify
   `~/.tripwire/logs/<project-slug>/` directory gets the right
   slug (not `unknown/`). Regression test for H1.
5. `tripwire session spawn <id>` twice on the same session (once
   fresh, once after a pause); confirm only **one**
   `CLAUDE.md.bak.*` file ever exists. Regression test for H2.
6. `bash scripts/smoke-subprocess-runtime.sh` — passes against a
   real-claude-installed host (H7).
7. `bash scripts/smoke-subprocess-resume.sh` — passes; agent picks
   up prior context after `--resume` (H7).
8. `gh pr view 16 --json body` shows the refreshed body (H9).

## Scope — explicitly out

- **No runtime-level changes** beyond the targeted bugs.
  `subprocess` and `manual` are the two runtimes; container mode
  stays future.
- **No schema migration.** `last_spawn_resumed` defaults to False
  for existing sessions; CLAUDE.md sentinel is additive.
- **No changes to `session complete` / PR flow.** That's the prior
  correction's territory (F8, already shipped).
- **Summary as a standalone binary.** H6 lives as a subcommand,
  not a new tool.
- **Rewriting history in specs/plans docs.** Correction preambles
  are the mechanism; tmux grep residue in `docs/` is out of H8
  scope.

## Rollback

Each phase is self-contained and revertable:

- H1–H4 touch 1–3 files each; `git revert <sha>` restores prior
  behaviour without affecting other phases.
- H5/H6 are additive subcommands + new modules; revertable.
- H7 is purely additive (scripts + one spec edit); revert is
  trivial.
- H8 is cosmetic — a mechanical docstring/comment edit with no
  behavioural change; revert is trivial.
- H9 runs on the hosted PR metadata; re-edit via `gh pr edit` if
  wrong.
