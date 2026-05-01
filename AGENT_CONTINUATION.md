# Agent Continuation: JIT Prompts Terminology Branch

This file is the crash-recovery handoff for the in-progress JIT prompt rename.
Read it first before continuing work in this worktree.

## Current State

- Main checkout: `/Users/maia/Code/seido/tripwire/tripwire`
- Feature worktree: `/Users/maia/Code/seido/tripwire/tripwire/.claude/worktrees/jit-prompts-terminology`
- Branch: `feat/jit-prompts-terminology`
- Base commit: `dfd6a75`
- Base remote: `origin/main`
- Target package version: `0.9.3`
- Previous dirty-main work was saved in the main checkout as:
  `stash@{0}: On main: salvage aborted jit-prompts rename from dirty main`

The feature worktree contains the v0.9-aware rename from prompt-style
`tripwire` to `jit_prompt`. Many renamed files are still untracked, so
`git diff` alone underreports the patch. Use:

```bash
git status --short --branch
git ls-files -o --exclude-standard
```

before making decisions. As of the latest checkpoint, the prompt rename is
implemented across the v0.9 Python/backend/frontend workflow surface. Python
lint and the full Python test suite pass. Targeted frontend tests for the
renamed workflow/event surfaces pass, and the frontend production build passes
with the existing large-chunk warning.

## Recovery Rules

- Work only in `.claude/worktrees/jit-prompts-terminology`.
- Do not mutate `main` from this branch.
- Do not apply `stash@{0}` wholesale. It is stale reference material from the
  aborted edit on main.
- Do not run parallel commands that touch git metadata, such as `git fetch`,
  `git stash`, `git merge`, or `git worktree`.
- Prefer small repair/test cycles. After each meaningful checkpoint, update this
  file with the new command result and next failure.
- Do not broaden the branch scope. This branch is for the v0.9 prompt-primitive
  rename only.

## Terminology Contract

- Product/package/on-disk namespace remains `Tripwire` / `tripwire` /
  `.tripwire`.
- Prompt-delivery primitive becomes `JIT prompt` in user copy and `jit_prompt`
  in code/config/event fields.
- Detector-style validation, hook, monitor, and watcher findings may still use
  `tripwire` terminology.
- Hard migration remains the rule: no compatibility aliases for old prompt
  config keys, commands, modules, or event names.

## What Has Been Started

The previous agent moved or renamed the prompt-primitive files and many related
tests/docs:

- `src/tripwire/_internal/tripwires/` -> `src/tripwire/_internal/jit_prompts/`
- `src/tripwire/cli/tripwires.py` -> `src/tripwire/cli/jit_prompts.py`
- `src/tripwire/cli/test_tripwire.py` -> `src/tripwire/cli/test_jit_prompt.py`
- `src/tripwire/core/tripwire_state.py` -> `src/tripwire/core/jit_prompt_state.py`
- `docs/*tripwire-authoring*` -> `docs/*jit-prompt-authoring*`
- many `*_tripwire.py` tests -> `*_jit_prompt.py`

The prompt rename is functionally repaired across the targeted Python/backend
and frontend workflow/event surfaces. Remaining work before review is mostly
diff review, optional staging/commit, and deciding whether to address unrelated
repo-wide frontend lint debt in a separate branch.

## Repair Status

1. Moved JIT prompt package: done.
   - Rename base class `Tripwire` to `JitPrompt`.
   - Rename `tripwire_id` fields/params to `jit_prompt_id` where they refer to
     prompt delivery.
   - Rename `tripwires` locals to `jit_prompts`.
   - Rename event payloads and event dirs from prompt-style names:
     `tripwire_fire`, `tripwire.fired`, `firings`, and `tripwire_id` should
     become JIT prompt names where they are produced by
     `_internal/jit_prompts`.
   - Keep `.tripwire/` as the disk namespace.
   - Latest status: repaired and covered by
     `tests/unit/internal/test_jit_prompt_registry.py`.

2. Loader/config plumbing: done.
   - `load_jit_prompt_registry` should return `dict[str, list[JitPrompt]]`.
   - `_read_tripwires_block` should become `_read_jit_prompts_block`.
   - It must read `project.jit_prompts`, not `project.tripwires`.
   - Local module import prefixes and errors should say JIT prompt.
   - Station registration should call renamed workflow-registry functions.

3. CLI entrypoints: done.
   - Root commands are `jit-prompts` and `test-jit-prompt`.
   - `session complete` uses `--jit-prompt-id` and `--no-jit-prompts`.

4. Workflow schema/registry/transitions/drift: done.
   - Prompt station references are `jit_prompts`.
   - Prompt workflow event is `jit_prompt.fired`.
   - Detector-style validator/hook tripwire wording remains separate.

5. Backend UI service and frontend workflow types: done.
   - `/api/workflow` prompt lane is `jit_prompts`.
   - Prompt-specific workflow cards/copy use JIT prompt terminology.

6. Tests: targeted and full Python verification passed. Targeted frontend
   workflow/event tests and production build passed.

## Stale-Name Search

Use this search repeatedly. Every match should be classified as either a real
remaining prompt rename, detector-style tripwire terminology to keep, or a test
that still needs migration. Do not include this continuation file in the scan,
because it intentionally documents removed names for recovery context.

```bash
rg -n "tripwire\._internal\.tripwires|_internal/tripwires|TripwireContext|SelfReviewTripwire|PhaseTransitionTripwire|FollowupsNotFiledTripwire|StoppedToAskTripwire|WriteCountTripwire|CostCeilingTripwire|load_registry|fire_event|tripwire_state|--no-tripwires|--tripwire-id|project\.yaml\.tripwires|tripwires\.enabled|tripwires\.extra|tripwire_bypass|tripwire_fire|tripwire\.fired|tripwires:" src tests docs .github pyproject.toml
```

Latest scan result: outside this continuation file, the removed prompt-specific
names above are clean. Detector-style `tripwire_id` references remain in monitor
and watcher code by design.

## Verification Ladder

Latest verification results:

- `uv run ruff check src tests`: passed.
- `uv run pytest -q`: passed, 2664 passed, 4 deselected, 14 Pydantic warnings.
- JIT prompt internal/integration target:
  `uv run pytest -q tests/unit/internal/test_jit_prompt_registry.py tests/unit/internal/test_ack_flow.py tests/unit/internal/test_*jit_prompt*.py tests/integration/test_deviation_jit_prompts.py`
  passed, 111 passed.
- CLI/workflow target:
  `uv run pytest -q tests/unit/cli/test_*jit_prompt*.py tests/unit/cli/test_session_complete_jit_prompt.py tests/unit/cli/test_workflow_transition_cli.py tests/unit/core/test_workflow_schema.py tests/unit/core/test_workflow_drift.py tests/unit/core/test_workflow_jit_prompt_registration.py tests/unit/core/test_workflow_events_log.py`
  passed, 88 passed.
- Frontend workflow/event target:
  `npm test -- src/__tests__/features/workflow src/__tests__/api/workflow.test.tsx src/__tests__/api/sessionEvents.test.ts src/__tests__/features/events/test_EventLog.test.tsx src/__tests__/features/live/test_LiveRail.test.tsx src/__tests__/features/live/test_TurnStream.test.tsx src/__tests__/features/live/test_useLiveSession.test.tsx src/__tests__/features/process-quality/test_ProcessQuality.test.tsx src/__tests__/features/sessions/test_SessionEventFeed.test.tsx src/__tests__/lib/realtime/eventHandlers.test.ts`
  passed, 82 passed.
- `npm run build`: passed; Vite still warns the main JS chunk is larger than
  500 kB.
- Full frontend lint through the main checkout's Biome binary still fails on
  unrelated repo-wide diagnostics outside the touched workflow/event files:
  existing non-null assertions, graph/drift/project/session formatting, and
  array-index key warnings. The touched file subset was checked with
  `biome check --write` and is clean.

Useful commands to rerun:

```bash
uv run pytest -q tests/unit/internal/test_jit_prompt_registry.py
uv run pytest -q tests/unit/internal/test_*jit_prompt*.py
uv run pytest -q tests/unit/cli/test_*jit_prompt*.py tests/unit/cli/test_session_complete_jit_prompt.py
uv run pytest -q tests/unit/core/test_workflow_schema.py tests/unit/core/test_workflow_drift.py tests/unit/core/test_workflow_jit_prompt_registration.py
uv run pytest -q tests/ui/services/test_workflow_service.py tests/ui/routes/test_workflow_route.py
uv run pytest -q tests/unit/internal/test_pre_push_hook.py tests/unit/internal/test_module_hygiene.py tests/ui/services/test_workflow_service.py tests/ui/routes/test_workflow_route.py
uv run ruff check src tests
uv run pytest -q
```

Frontend checks after backend/API shape is repaired:

```bash
npm run lint
npm test -- src/__tests__/features/workflow
npm run build
```

Run frontend commands from `web`. This worktree may not have `web/node_modules`;
if local frontend checks fail with `vitest: command not found`, install deps or
temporarily symlink `web/node_modules` from the main checkout's existing
frontend install.

## Out Of Scope For This Branch

The original single-slice JIT prompt branch scope has been widened: keep PR #83
open and continue the remaining cleanup work on this branch.

## Commit Readiness Checklist

- `git status --short` shows renamed files staged/tracked intentionally.
- No prompt-primitive import path remains under `_internal/tripwires`.
- No prompt public config remains as `project.yaml.tripwires`.
- No prompt CLI command remains as `tripwires` or `test-tripwire`.
- `--jit-prompt-id` and `--no-jit-prompts` are the only prompt session-complete
  flags.
- Targeted JIT prompt tests pass.
- Full Python verification has either passed or has a documented unrelated
  blocker.
- Frontend workflow checks have either passed or have documented unrelated
  blockers.
