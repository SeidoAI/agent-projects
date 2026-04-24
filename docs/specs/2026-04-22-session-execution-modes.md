# Session execution modes (subprocess + manual)

**Status:** implemented on `feat/v0.7.2-tmux` (PR #16) after two mid-stream corrections — see below
**Authors:** sean@seido.dev + Claude Opus 4.7
**Date:** 2026-04-22, 2026-04-23

## Correction (2026-04-23) — tmux reverted to subprocess

After landing the tmux runtime and running a real-claude probe, we hit
four structural issues that together made tmux unfit for production:

1. **Workspace-trust gate.** Claude's interactive mode blocks on an
   Enter-to-accept dialog in every fresh cwd (= every tripwire
   worktree). Neither `--dangerously-skip-permissions`, `--bare`, nor
   `--add-dir` bypasses it. Only `-p` mode skips the dialog (claude's
   own CLI help documents this).
2. **`tmux send-keys` interprets newlines as Enter.** Multi-line
   prompts got split into many user turns. Required `load-buffer` /
   `paste-buffer`; fragile to verify.
3. **`tmux capture-pane` strips trailing whitespace per line.** The
   default `_READY_MARKER = "> "` cannot match what real claude
   emits. The real claude ready marker is UI-version-sensitive and
   needs re-probing every release.
4. **Hard tmux dependency** plus a two-phase ready-probe state
   machine (detect trust → send Enter → wait for ready).

Weighed against the actual architecture — the executor agent is
autonomous, opens a PR when done, and exits; the PM reviews on
GitHub — none of these costs bought us anything. The "live mid-run
attach + input" feature that motivated tmux wasn't a real
requirement.

**Pivot: `SubprocessRuntime` using `claude -p` + log file.** `-p`
auto-skips the trust dialog, takes the prompt as an argv string
(no newline quirks), emits `stream-json` to a log file we `tail -f`
for live observation. No tmux, no ready-probe, no send-keys.

The jsonl-corruption and resume-broken claude bugs that originally
ruled out `-p` in the earlier spec fire only when a second `claude
--resume` process runs against a live session. Since `tripwire
session attach` is now `tail -f <log>` (a pure reader), no second
process ever touches the jsonl. **Additionally:** an empirical probe
against claude 2.1.117 found that `claude -p <prompt> --resume
<uuid>` (with no `--session-id`) works correctly — issue #2354 is
fixed. We had a latent bug in `build_claude_args` that sent both
`--session-id` and `--resume` (which claude rejects); that's now
fixed too.

**Stop-and-ask semantics** hardened empirically: `AskUserQuestion`
and `SendUserMessage` both fail in `-p` mode (no TTY to answer),
and the agent retry-loops on the `is_error` sentinel until
`--max-turns` exhausts. Fix: those tools go on the default
`disallowed_tools` list, so the agent falls back to plain-text
"here's what I can't figure out" and exits 0. The PM reads the log,
updates the plan, spawns again with `--resume`.

**Removed in this correction:**

- `src/tripwire/runtimes/tmux.py` (entire file, deleted)
- `tests/unit/test_runtimes_tmux.py`
- `tests/fixtures/fake_tmux.py`
- `fake_tmux_on_path` fixture
- `RuntimeState.tmux_session_name` field
- `RuntimeStartResult.tmux_session_name` field
- V0.7 pid-fallback branches in `session_pause_cmd` / `session_abandon_cmd`

**Added in this correction:**

- `src/tripwire/runtimes/subprocess.py` — `SubprocessRuntime`
- `SpawnDefaults.resume_prompt_template` + `render_resume_prompt`
- Resume kickoff template (short continuation cue, not full plan.md
  re-render) — claude's own jsonl carries the prior conversation
- `AskUserQuestion` + `SendUserMessage` in default `disallowed_tools`
- "headless mode" clause in the prompt template exit protocol
- Resume-argv fix in `build_claude_args`: drop `--session-id` when
  `resume=True`

**Default runtime is now `subprocess`.** The `manual` runtime stays
as a prep-only escape hatch. `tmux` is not a valid runtime value.

**Known limitation — process-group handling.** `SubprocessRuntime`
sends SIGTERM to the claude pid directly, not to its process group.
If a future claude (or an MCP server claude spawns) installs its
own SIGTERM handler or double-forks to detach, those children will
outlive `pause`/`abandon`. Empirically non-issue for claude 2.1.x.
Mitigation is one line: `start_new_session=True` is already passed
to `Popen`, so we can switch to `os.killpg(pid, SIGTERM)` when this
becomes a real problem.

---

## Correction (2026-04-22 afternoon)

The original spec put PR creation inside `tripwire session complete`
(see §"Dual-PR at `session complete`" below, §Decisions 8, and parts of
§Architecture / §Components). **This was wrong.** The implementation
shipped it that way, and three independent code reviews (self, Codex,
superpowers code-reviewer) flagged the ordering conflict: the existing
`_verify_pr_merged` gate aborts the command before `run_pr_flow` can
open the PRs, so first-ever `session complete` invocations fail unless
the PM explicitly bypasses all gates.

The real model:

- The **executor agent opens the PR(s) when it finishes.** PR-open is
  the exit signal to the PM that the agent is done.
- For multi-worktree sessions, the agent opens one PR per worktree
  with commits (typically: the code PR and the project-tracking PR),
  cross-linked in the bodies.
- `tripwire session complete` stays as the PM's post-merge
  finalization step. `_verify_pr_merged` is the correct gate. It
  requires the PM (or auto-merge on GitHub) to have merged before
  tripwire transitions the session to `done`.

The exit protocol is instructed in the shipped prompt template
(`src/tripwire/templates/spawn/defaults.yaml`). No code in tripwire
opens PRs.

**Removed from the design:**

- `src/tripwire/core/session_pr_flow.py` (entire file, reverted)
- `AgentSession.merge_policy` field
- `AgentSession.commit_on_complete` field
- `EngagementEntry.pr_urls` field
- `session complete` `--skip-pr-flow` / `--skip-pr-flow-push` flags

**Retained from the design** (still correct, post-2026-04-23 pivot):

- Pluggable `SessionRuntime` registry (subprocess + manual; tmux
  is no longer a runtime — see the 2026-04-23 correction above)
- Runtime-agnostic prep pipeline (worktrees + skill copy + CLAUDE.md + kickoff.md)
- `tripwire session attach` subcommand
- Schema additions: `SpawnInvocation.runtime`, `RuntimeState.skills_hash`
  (`RuntimeState.tmux_session_name` was removed in the 2026-04-23 pivot)

The rest of this document describes the original (flawed) dual-PR
design and its rationale. Keep for historical context; do not read as
current truth. The sections that remain fully accurate:
§Non-goals, §Decisions 1–7, §Architecture (ignore the "At `session
complete`..." line), §`SessionRuntime` protocol, §Prep pipeline,
§Runtime: `TmuxRuntime`, §Runtime: `ManualRuntime`, §`tripwire
session attach`, §Error handling summary rows for runtime concerns,
§Migration / backwards compat.

---

## Context

v0.7 shipped `tripwire session spawn`, which launches a Claude Code
agent for a session via `subprocess.Popen(["claude", "-p", "<prompt>",
...])`. In practice, PMs have not been using it — they hand-craft
prompts and paste them into fresh Claude Code terminals, manually
pointing the agent at session artifacts by absolute path. A live test
with a packaged `backend-development` skill revealed why: the skill
was never surfaced to the agent because nothing at session runtime
told Claude Code it existed. The template files inside
`src/tripwire/templates/skills/` are data, not a mounted
`.claude/skills/` directory, and `session spawn` doesn't mount them.

A deeper investigation of Claude Code's session model surfaced three
further constraints that shape this design:

- **`claude --resume` on a live `-p` process corrupts the session
  jsonl.** GitHub [#26964](https://github.com/anthropics/claude-code/issues/26964)
  documents 23–77% cross-session contamination. No file locking exists.
- **`claude --resume` after a `-p` exit is unreliable.**
  [#2354](https://github.com/anthropics/claude-code/issues/2354) (open)
  reports resume broken in `-p` mode; [#36583](https://github.com/anthropics/claude-code/issues/36583)
  reports 25% history loss from messageId collisions.
- **Worktree session files land under a separate
  `~/.claude/projects/<worktree-hash>/` directory keyed on cwd, not
  git root.** ([#34437](https://github.com/anthropics/claude-code/issues/34437))
  Fine as long as `attach` cds to the same worktree as `spawn`.

These constraints rule out the "subprocess background + resume later"
pattern entirely: both the live-attach and post-hoc-resume flows are
either corruption-prone or broken. The only safe path for a human to
observe or drive an agent is a single Claude Code process holding the
session file, running inside a **tmux** session the human can attach
to.

This spec replaces the existing `-p` subprocess launcher with a
pluggable runtime model whose live runtime is tmux. It also closes
the loop on the orthogonal dual-PR workflow: sessions that touch both
the code repo and the project-tracking repo should produce two
reviewable PRs at `session complete`, cross-linked, driven by the
already-multi-worktree session model.

## Goals

- Launch Claude Code sessions in a way where the agent **sees its
  declared skill(s)** without any manual setup step.
- Give PMs a config knob (`session.yaml.spawn_config.invocation.runtime`)
  to choose between a live-attachable session (`tmux`) and a
  prepared-but-not-launched session (`manual`).
- Keep the kickoff prompt **auditable and single-source-of-truth**:
  authored in the session's `plan.md` (top section), rendered into the
  prompt via the existing `render_prompt({plan})` pipeline.
- Use the **existing multi-worktree data model** to drive dual-PR
  completion: session declares `repos: [code_repo, project_repo]`,
  spawn creates two worktrees, complete produces two PRs.
- Delete the `-p`-based Popen launch path in `session_spawn_cmd` —
  new launches only go through the runtime registry. (The argv-builder
  helpers in `build_claude_args` stay and are extended with an
  `interactive: bool` flag.)

## Non-goals

- Container / remote orchestration (`agent-containers.md` describes
  this as future work).
- Remote-control mode — claude.ai tunnel support is out of scope.
- Auto-open PR review UI / surface reviews inside tripwire.
- Generating session prompts on the fly. PMs author `plan.md`'s top
  section by hand; this is intentional for traceability and auditability.
- Migrating in-flight v0.7 sessions. Mid-flight sessions at the time
  of the upgrade finish their lifecycle under the old PID-tracking
  fallback. New sessions use the new runtime model.

## Decisions locked in during brainstorming

1. **tmux is the only live runtime.** Dropping subprocess is
   intentional: `-p` plus `--resume` is structurally unsafe (#26964,
   #2354, #36583). Background-only fire-and-forget is not a use case
   we want to support at the CLI level.
2. **`manual` is kept** as a prep-only escape hatch for dry-runs,
   debugging, tmux-unavailable environments, and "I want to inspect
   the worktree before launching myself" workflows.
3. **Default runtime is `tmux`.** If tmux is absent, prep errors with
   a clear install-or-switch-to-manual message. No silent fallback.
4. **Kickoff prompt lives in `sessions/<id>/plan.md`'s top section.**
   The existing `spawn_config.prompt_template` defaults to `{plan}`,
   which passes plan.md verbatim. Agents reuse PM-authored boot
   boilerplate by convention (template/example owned by the PM skill),
   not by runtime-time concatenation. Single source, full git
   auditability.
5. **Mode lives at `session.spawn_config.invocation.runtime`.** Extends
   the existing resolution chain (shipped default → project file →
   project.yaml → session.yaml). No new parallel config block.
6. **Skills are copied, not symlinked.** Sessions are ephemeral;
   live-edit-during-session is not a supported pattern.
7. **Planning artifacts are referenced via the project-tracking
   worktree, not copied.** That worktree is itself tripwire-managed
   (entry in `session.repos`), so the agent reads and writes the
   authoritative location directly — no sync-back problem.
8. **`tripwire session complete` produces two PRs** (one per worktree
   with changes), cross-linked. Merge policy is session/project
   configurable (`await_review | auto_merge_on_green | auto_merge_immediate`).

## Architecture

Three layers:

```
┌──────────────────────────────────────────────┐
│  tripwire session spawn / attach / complete  │   CLI surface
└──────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────┐
│  Prep pipeline  (runtime-agnostic)           │
│  - resolve SpawnConfig                       │
│  - create worktrees (one per session.repos)  │
│  - copy skills into .claude/skills/          │
│  - render CLAUDE.md                          │
│  - render prompt ({plan} -> plan.md)         │
└──────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────┐
│  Runtime dispatcher                          │
│  RUNTIMES[spawn_config.invocation.runtime]   │
└──────────────────────────────────────────────┘
           │                        │
           ▼                        ▼
      TmuxRuntime              ManualRuntime
      (live-attach)            (prep-only)
```

At `session complete`, a post-run step iterates each worktree and
opens PRs — runtime-agnostic, only reads state from
`runtime_state.worktrees`.

## Components

```
src/tripwire/runtimes/
  __init__.py          # RUNTIMES registry
  base.py              # SessionRuntime protocol, RuntimeState types
  tmux.py              # TmuxRuntime
  manual.py            # ManualRuntime
  prep.py              # copy_skills, render_claude_md, resolve_worktrees

src/tripwire/templates/worktree/
  CLAUDE.md.j2         # per-session CLAUDE.md template
  # (kickoff preamble lives in the PM skill's examples/,
  #  not in this runtime layer)

src/tripwire/cli/session.py
  # spawn refactored:
  #   prep.run(session, resolved, ...) -> PreppedSession
  #   RUNTIMES[runtime_name].start(prepped)
  # new `attach` subcommand:
  #   RUNTIMES[runtime_name].attach_command(state) -> execvp
  # complete extended:
  #   for each worktree with dirty tree, commit+push+pr
  #   cross-link the PRs, persist urls to engagements

src/tripwire/core/spawn_config.py
  # SpawnInvocation.runtime: Literal["tmux", "manual"] = "tmux"

src/tripwire/core/complete.py       # new — dual-PR orchestration
```

### `SessionRuntime` protocol (`runtimes/base.py`)

```python
class SessionRuntime(Protocol):
    name: str

    def validate_environment(self) -> None:
        """Raise with a user-facing message if the runtime cannot run
        on this host (e.g. tmux missing). Called at prep time before
        any filesystem mutation."""

    def start(self, prepped: PreppedSession) -> RuntimeState:
        """Launch the agent process. Returns state to persist."""

    def pause(self, state: RuntimeState) -> None: ...
    def abandon(self, state: RuntimeState) -> None: ...
    def status(self, state: RuntimeState) -> Literal["running", "exited", "unknown"]: ...
    def attach_command(self, state: RuntimeState) -> AttachCommand:
        """Return either an execvp argv (tmux) or an InstructionEcho
        (manual) that `tripwire session attach` dispatches on."""
```

`RuntimeState` is a loose TypedDict each runtime extends with its own
fields. `claude_session_id` and `worktrees` are shared fields.

## Schema changes

### `SpawnInvocation`

```python
class SpawnInvocation(BaseModel):
    command: str = "claude"
    runtime: Literal["tmux", "manual"] = "tmux"
```

Resolution chain unchanged (shipped default → `.tripwire/spawn/defaults.yaml`
→ `project.yaml.spawn_defaults` → `session.yaml.spawn_config`). Per-session
override beats project default beats shipped default.

### `RuntimeState`

```python
class RuntimeState(BaseModel):
    claude_session_id: str | None = None
    worktrees: list[WorktreeEntry] = []
    started_at: str | None = None
    # tmux-runtime fields
    tmux_session_name: str | None = None

    # legacy (pre-v0.8) fields — still serialised/deserialised so
    # mid-flight v0.7 sessions can be paused/abandoned. New sessions
    # leave these null.
    pid: int | None = None
    log_path: str | None = None
```

### `Session`

```python
class Session(BaseModel):
    ...
    merge_policy: Literal["await_review", "auto_merge_on_green", "auto_merge_immediate"] = "await_review"
    commit_on_complete: Literal["auto", "manual"] = "auto"
```

Both default to values that preserve today's human-in-the-loop
behaviour (no auto-merge, auto-commit is fine because `complete` only
runs when the PM calls it).

## Prep pipeline

Runs once, before any runtime start. Produces a `PreppedSession`
dataclass: code-worktree path, all worktrees, rendered prompt,
system-append, session id, claude session uuid, resolved spawn
defaults.

Steps in order:

1. **Validate environment.** `RUNTIMES[name].validate_environment()`.
   Fails fast before any state mutation.
2. **Resolve worktrees.** For each `session.repos[]` entry, resolve
   the local clone path, compute the worktree path, `git worktree add`
   if it doesn't exist. Existing logic in `session.py:563-595` moves
   into `prep.py:resolve_worktrees`. **The first entry in
   `session.repos` is the code worktree** — the agent cds into it and
   `CLAUDE.md` is rendered at its root. Additional entries (typically
   the project-tracking repo) are available to the agent via absolute
   paths rendered into `CLAUDE.md`. This is an authoring convention,
   not a schema field — PMs author session.yamls with the code repo
   first.
3. **Copy skills.** For each skill in `agents/<agent_id>.yaml.context.skills`,
   copy from `importlib.resources("tripwire.templates.skills")/<name>/`
   into `<code-worktree>/.claude/skills/<name>/`. Overwrite with
   backup if destination exists. Append `.claude/` and `.tripwire/`
   to `<code-worktree>/.git/info/exclude` (worktree-local gitignore,
   never committed) so these tripwire-managed directories don't
   pollute the operator's `git status` or accidentally land in a
   commit. If the entries are already present, skip.
4. **Render CLAUDE.md.** Jinja template renders to
   `<code-worktree>/CLAUDE.md`, containing: agent identity, skill
   references (`.claude/skills/<skill>/SKILL.md`), session plan path
   (absolute, in the project-tracking worktree), issue spec paths,
   verification-checklist path, "how to report progress" pointers.
   Backup + overwrite if CLAUDE.md exists.
5. **Render prompt + kickoff.** Existing `render_prompt(resolved,
   plan=plan_md_content)` unchanged — template defaults to `{plan}`.
   The rendered prompt is also written to
   `<code-worktree>/.tripwire/kickoff.md` so the operator has a
   pastable file for manual-mode launch and the tmux ready-probe
   timeout recovery path.

If any step fails, prep cleans up any files it created during this
run (partial worktree creation is left intact — those are git
operations, operator-recoverable via `git worktree remove`).

## Runtime: `TmuxRuntime`

```python
class TmuxRuntime:
    name = "tmux"

    def validate_environment(self) -> None:
        if shutil.which("tmux") is None:
            raise click.ClickException(
                "tmux runtime requires tmux on PATH. "
                "Install tmux, or set spawn_config.invocation.runtime: manual."
            )

    def start(self, prepped: PreppedSession) -> RuntimeState:
        session_name = f"tw-{prepped.session_id}"
        # build_claude_args grows an `interactive: bool = False` kwarg:
        # when True, it omits `-p <prompt>` and returns argv for an
        # interactive claude. Prompt is delivered via send-keys after
        # the ready-probe.
        claude_args = build_claude_args(
            prepped.spawn_defaults,
            prompt=None,
            interactive=True,
            system_append=prepped.system_append,
            session_id=prepped.session_id,
            claude_session_id=prepped.claude_session_id,
        )

        subprocess.run([
            "tmux", "new-session", "-d",
            "-s", session_name,
            "-c", str(prepped.code_worktree),
            "--", *claude_args,
        ], check=True)

        _wait_for_claude_ready(session_name, timeout=10)
        subprocess.run([
            "tmux", "send-keys", "-t", session_name,
            prepped.prompt, "Enter",
        ], check=True)

        return RuntimeState(
            tmux_session_name=session_name,
            claude_session_id=prepped.claude_session_id,
            worktrees=prepped.worktrees,
            started_at=now_iso(),
        )
```

**Ready-probe:** `_wait_for_claude_ready` polls `tmux capture-pane -pt
<session>` at 250ms intervals for up to 10s, looking for claude's
interactive ready marker (`> ` prompt; exact string verified
empirically and pinned in a constant with a comment). On timeout,
leaves the tmux session running and raises with guidance:
`"claude did not reach ready prompt within 10s. Attach with
'tripwire session attach <id>' and paste the prompt from
<kickoff path>."` The kickoff prompt is written to
`<code-worktree>/.tripwire/kickoff.md` as part of prep for this
recovery case and for the manual runtime.

**Pause:** `tmux send-keys -t <name> C-c` (interrupts the current
turn; claude returns to prompt).

**Abandon:** `tmux kill-session -t <name>`.

**Status:** `tmux has-session -t <name>` exit code: 0 → `running`;
non-zero → `exited`.

**Attach command:** `["tmux", "attach", "-t", <name>]`.

## Runtime: `ManualRuntime`

```python
class ManualRuntime:
    name = "manual"

    def validate_environment(self) -> None: ...  # no-op

    def start(self, prepped: PreppedSession) -> RuntimeState:
        click.echo("Prepared. To launch, run:")
        click.echo(f"  cd {prepped.code_worktree}")
        click.echo(f"  claude --name {prepped.session_id} "
                   f"--session-id {prepped.claude_session_id}")
        click.echo(f"\nKickoff prompt: {prepped.code_worktree}/.tripwire/kickoff.md")
        return RuntimeState(
            claude_session_id=prepped.claude_session_id,
            worktrees=prepped.worktrees,
            started_at=now_iso(),
        )

    # pause / abandon: no-op + warn
    # status: always "unknown"
    # attach_command: echo the start command
```

Prep still writes `<code-worktree>/.tripwire/kickoff.md` so the
operator has the prompt in a pastable file.

## `tripwire session attach <id>`

New subcommand. `AttachCommand` is a discriminated union:

```python
@dataclass
class AttachExec:
    argv: list[str]                # execvp target (tmux runtime)

@dataclass
class AttachInstruction:
    message: str                   # human-facing instruction (manual runtime)

AttachCommand = AttachExec | AttachInstruction

@session.command("attach")
@click.argument("session_id")
def session_attach_cmd(session_id: str) -> None:
    session = _load_session(session_id)
    runtime = RUNTIMES[session.spawn_config.invocation.runtime]
    cmd = runtime.attach_command(session.runtime_state)
    match cmd:
        case AttachExec(argv):
            os.execvp(argv[0], argv)   # pty handover, never returns
        case AttachInstruction(message):
            click.echo(message)
```

For tmux: clean pty handover via `execvp` — the operator's shell
becomes the tmux-attached terminal. For manual: prints the command
and the kickoff path; the operator runs it themselves.

## Dual-PR at `session complete`

Post-gates, post-issue-close orchestration in a new
`core/complete.py:run_pr_flow`. Invoked from the existing
`session complete` command after the current validation step, before
cleanup.

```
for wt in session.runtime_state.worktrees:
    if git_dirty(wt.worktree_path):
        if session.commit_on_complete == "auto":
            git commit -am "<render commit_message_template>"
        else:  # "manual"
            abort(f"Worktree {wt.worktree_path} has uncommitted changes "
                  "and session.commit_on_complete is 'manual'. "
                  "Commit or discard, then rerun.")
    if branch_has_new_commits_vs_base(wt):
        git push origin <wt.branch>
        existing = find_existing_pr(wt.repo, wt.branch)   # idempotent rerun
        if existing is None:
            pr_url = gh pr create --repo <wt.repo> \
                                  --base <wt.base_branch> \
                                  --head <wt.branch> \
                                  --title <...> --body <...>
        else:
            pr_url = existing.url
        engagement = _engagement_for_repo(session, wt.repo)  # new helper
        engagement.pr_url = pr_url
    else:
        note(f"No changes in {wt.repo}, skipping PR.")

# second pass: edit each PR body to cross-link the sibling(s)
for engagement in session.engagements:
    if engagement.pr_url:
        gh pr edit <pr_url> --body <body with sibling PR urls>

# merge policy
if session.merge_policy == "auto_merge_on_green":
    for pr_url in pr_urls: gh pr merge --auto --squash <pr_url>
elif session.merge_policy == "auto_merge_immediate":
    for pr_url in pr_urls: gh pr merge --squash <pr_url>
# else await_review: do nothing
```

PR body template lives at `src/tripwire/templates/pr/session_complete.md.j2`
and includes: session id, issues closed, verification-checklist summary,
sibling PR link placeholder (filled on second pass).

Partial-failure handling:

- Commit fails in one repo → abort, session stays `completing`,
  explicit recovery commands printed.
- Push fails → same.
- `gh pr create` succeeds for one repo, fails for the other → session
  stays `completing`, first PR is not closed, explicit recovery
  commands printed.

No automatic rollback — PR creation is idempotent only if the operator
re-runs `session complete`, and the implementation detects
already-open PRs on the same branch and skips to cross-linking.

## Error handling summary

| Condition | Behaviour |
|---|---|
| tmux not installed | Prep errors before any state mutation |
| Skill not in package resources | Prep errors, names the missing skill |
| `.claude/skills/` already populated | Overwrite with `.claude/skills.bak.<ts>/`, warn |
| `CLAUDE.md` already exists | Overwrite with `CLAUDE.md.bak.<ts>`, warn |
| tmux send-keys ready-probe timeout | Error, tmux session left running, kickoff path printed |
| Code worktree path collision | Existing spawn error, unchanged |
| One PR succeeds, one fails | Partial success printed, session stays `completing` |
| `session complete` rerun after partial success | Detect already-open PRs, skip to cross-link |

## Testing

### Unit tests per runtime

- `tmux.py` — fake `tmux` CLI shim on PATH, assert argv, send-keys
  contents, ready-probe polling logic, timeout path, pause/abandon
  argv.
- `manual.py` — pure string-rendering assertions on the echo output.
- `prep.py` — temp worktrees + skill copy fidelity + CLAUDE.md render
  + backup-on-collision behaviour + kickoff.md written.

### Unit tests for dispatcher

- Unknown runtime name → clear error.
- Default resolution when unset.
- Per-session override beats project default.

### Integration tests

- **tmux runtime** (gated on `shutil.which("tmux")`) — real tmux
  session against a fixture worktree; verify `attach` works; verify
  `pause`, `status`, `abandon` lifecycle.
- **Dual-PR flow** — fake `gh` on PATH; verify commit, push, PR
  create, cross-link edit, merge-policy branches, partial-failure
  messaging.

### Regression

- Single-repo session.yamls (no project-tracking repo in `repos`)
  still work: dual-PR step produces one PR, no cross-link.
- Existing prompt-template + `render_prompt` tests unchanged.
- Existing `SpawnConfig` resolution-chain tests extended with the
  new `runtime` field.

## Migration / backwards compat

- `invocation.runtime` absent in older session.yamls → defaults to
  `tmux`. If tmux is missing, operator sees the install-or-switch-to-manual
  error and sets `runtime: manual` in the session.yaml.
- In-flight v0.7 sessions (status `executing`) at upgrade time have
  `runtime_state.pid` referencing the old `-p` subprocess. `pause` /
  `abandon` retain a `pid`-based fallback path when
  `tmux_session_name` is absent, so mid-flight sessions can still be
  paused/abandoned under the old model — they just can't be spawned
  again under the old model.
- The `-p`-mode launch call (`subprocess.Popen([...], ...)` in the
  old `session_spawn_cmd`) is removed. New spawns only go through the
  runtime registry. Existing `claude -p` plumbing in
  `build_claude_args` / `spawn_config.py` stays (it's the basis for
  the `interactive: bool` extension).
- `SpawnDefaults.prompt_template` defaults unchanged (`{plan}` remains
  the canonical substitution).

## Follow-ups out of scope here

- **Container runtime** — slots in as a third `SessionRuntime` impl
  when `agent-containers` ships. Runtime protocol is designed for this
  extension.
- **Per-agent-type boot preamble** — an optional `agent.yaml` field
  (`kickoff_preamble_ref: path/to/preamble.md`) the prep pipeline
  prepends to plan.md for the prompt. Skipped here because the PM
  skill's templates/examples cover this via authoring convention.
- **PR review automation inside tripwire** — surface the two PRs'
  review state via `tripwire session status` or a new `tripwire pr
  status`. Sibling spec.
- **Auto-sync on mid-session plan.md edits** — today the prompt is
  rendered once at start; if the PM edits plan.md mid-session, the
  agent does not see the update. Out of scope; addressed by
  re-spawning with `--resume`.

## Verification plan

- Install tripwire from this branch into a fresh test project.
- Author a session.yaml declaring both the code repo and the
  project-tracking repo in `session.repos`, with an agent whose
  `context.skills` lists the expected skill(s).
- `tripwire session spawn <id>` — observe:
  - Both worktrees created.
  - `.claude/skills/<skill>/SKILL.md` present in the code worktree.
  - `CLAUDE.md` present and naming both worktrees.
  - `.tripwire/kickoff.md` present.
  - tmux session `tw-<id>` exists.
- `tripwire session attach <id>` → lands in the tmux-attached claude,
  can observe the agent and type to it.
- `tripwire session abandon <id>` → tmux session gone, no orphan
  processes.
- Let an agent run to completion. `tripwire session complete <id>`
  produces two PRs, cross-linked.
- `tmux kill-session -t tw-<id>` out of band, then `tripwire session
  attach <id>` → errors clearly with the tmux-session-not-found path,
  suggesting `session status` / `session cleanup` as remediation.
- Set `runtime: manual` on a session.yaml. `tripwire session spawn
  <id>` prints the command and does not launch. Pasting the command
  manually lands in an interactive claude. Session proceeds.
