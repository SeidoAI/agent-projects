# Tripwire v0.8 — tripwires as a first-class primitive

**Status**: idea (not yet designed in detail beyond this doc)
**Date**: 2026-04-21
**Depends on**: v0.7b Phase 6 (`tripwire session complete`)
**Source**: extended brainstorm on the four-lens self-review prompt
(2026-04-21 conversation). The mechanism we wanted for self-review
turned out to be a general-purpose primitive.

---

## 1. The problem

The tool ships three primitives today: phases, artifacts, sessions.
All three operate on **fully-disclosed** information — the agent
sees the plan, the verification checklist, the DoD, and the
acceptance criteria up front. The hope is that with full information,
the agent does great work.

The reality (observed across multiple PM reviews):

1. The agent reads everything and *plans to satisfy each visible
   criterion*. It optimises for what's checkable, not what's correct.
2. Late-session work is thinner than early-session work — the
   "fatigue pattern" already documented in `ANTI_PATTERNS.md`. The
   agent knows the verification checklist will run, so it ticks the
   boxes whether or not the underlying work has held up.
3. When asked "review your own work", the agent produces a
   performative review that finds nothing — because it knew the
   review was coming and pre-defended.
4. When the same agent is asked the same review questions *as a
   fresh task* (no prior framing), it readily finds 5–8 real bugs.

**The diagnostic insight:** the difference between performative
self-review and genuine self-review is whether the agent knew the
review was coming. Foreknowledge enables gaming; surprise produces
fresh-eyes engagement. This is the same dynamic that makes
unannounced security audits more effective than announced ones, and
why exam questions aren't pre-shared.

The current architecture has no way to express "X must happen, but
the agent must not know X is coming until it does." Every visible
artifact, every status transition, every DoD checkbox is by
definition known in advance.

## 2. The new primitive — tripwire

A **tripwire** is a piece of content (typically a prompt) that:

- Is registered against a **lifecycle event** (a CLI invocation, a
  status transition, a token/turn threshold)
- Is **invisible** to the executing agent until the event fires
- Is delivered to the agent as if it were a fresh request — usually
  by replacing what the agent expected to see (a routine "OK done"
  response) with the tripwire payload
- **Blocks** the lifecycle event from completing until the agent
  acknowledges it (typically by acting on it and re-invoking the
  command)

Tripwires sit alongside the existing primitives:

| Primitive | Purpose | Visibility to executing agent |
|---|---|---|
| **Phases** (`planning` → `in_progress` → `in_review` → `done`) | Where in the lifecycle we are | Always visible |
| **Artifacts** (`plan.md`, `verification-checklist.md`, etc.) | What the agent must read to do its job, and what it must produce as evidence | Visible at planning time; produced during execution |
| **Tripwires** (NEW) | What fires *at* the agent at a chosen lifecycle moment to prevent gaming | **Invisible** until fired |

Artifacts serve "make X knowable so the agent can execute against
it." Tripwires serve the opposite: "withhold X until the moment when
fresh-eyes engagement matters most." Both are needed; they don't
compete.

The naming reinforces the abstraction: a tripwire is *triggered* by
the agent itself stepping on it. The agent walks across the
lifecycle, hits a wire it didn't see, and the system fires.

## 3. Anatomy of a tripwire

A tripwire has four parts:

```python
# tripwire/_internal/tripwires/self_review.py

from tripwire._internal.tripwires import Tripwire, TripwireContext

class SelfReviewTripwire(Tripwire):
    id = "self-review"
    fires_on = "session.complete"        # the lifecycle event
    blocks = True                         # second call required after ack

    def fire(self, ctx: TripwireContext) -> str:
        """Return the prompt content to deliver to the agent."""
        return _FOUR_LENS_PROMPT_VARIATIONS[ctx.variation_index]

    def is_acknowledged(self, ctx: TripwireContext) -> bool:
        """Has the agent satisfied this tripwire?"""
        marker = ctx.project_dir / ".tripwire" / "acks" / f"{self.id}-{ctx.session_id}.json"
        return marker.is_file()
```

- **`id`** — unique, used in markers and logs
- **`fires_on`** — the lifecycle event that triggers it (see §4)
- **`blocks`** — if True, the firing event cannot complete until
  `is_acknowledged()` returns True
- **`fire(ctx)`** — returns the prompt text. May vary by context
  (project, session, agent, random seed)
- **`is_acknowledged(ctx)`** — checks whether the agent has
  satisfied the tripwire (typically by checking for a marker file
  the agent's response wrote)

## 4. Lifecycle events

Tripwires register against events. v0.8 supports five event kinds;
later versions can add more.

| Event | Triggered by | Typical tripwire |
|---|---|---|
| `session.complete` | Agent calls `tripwire session complete <id>` | Self-review (the canonical case) |
| `issue.close` | Agent calls `tripwire issue close <key>` | Substantiate-AC check |
| `pr.open` | Agent calls `gh pr create` (intercepted via wrapper) OR a post-create hook | Security trace, integrity sample |
| `validate.run` | Agent calls `tripwire validate` | Coverage tripwire if specific artifacts missing |
| `session.resume` | Agent calls `tripwire session resume <id>` after a CI failure | "What changed? What assumption broke?" |

A future v0.8.x could add **token-threshold** and **turn-threshold**
events fired by the spawn wrapper based on stream-json events — for
fatigue calibration mid-session. v0.8 ships event-driven only;
threshold-driven is deferred.

Each event can have multiple tripwires; they fire in registration
order. If any blocks and isn't acknowledged, the lifecycle event
itself fails.

## 5. Module layout

The whole point of a tripwire is to NOT be discoverable by the
agent. Implementation enforces this.

```
src/tripwire/
├── _internal/                       # leading underscore = "do not import from outside this package"
│   └── tripwires/
│       ├── __init__.py              # registry + base class
│       ├── manifest.yaml            # event → tripwire-class mapping
│       ├── self_review.py           # the four-lens prompt
│       ├── ac_substantiate.py       # the issue.close tripwire
│       ├── security_trace.py        # the pr.open security tripwire
│       └── ...
```

Constraints:

- Nothing inside `_internal/tripwires/` is exported from
  `tripwire/__init__.py`
- Nothing inside `_internal/tripwires/` is referenced by any
  user-facing template (no skill, no doc, no example)
- The `_internal/` prefix is the standard Python signal "external
  callers must not depend on this"; it also reads as a hint to
  agents skimming the codebase that this isn't where to look for
  workflow content

This is **not cryptographic** secrecy — an agent that grep's the
tripwire repo can find the prompts. But it raises the cost from
"loaded into context by default via skills" to "deliberately
searched for, against the spirit of `_internal/`." The freshness
benefit at the moment-of-completion is the primary win; module
hiding is a defence-in-depth.

### 5.1 Anti-gaming via variations

Each tripwire ships with N prompt variations. `fire(ctx)` picks one
based on a hash of `(project_id, session_id)`:

```python
_FOUR_LENS_PROMPT_VARIATIONS = [
    _PROMPT_V1,   # "You are doing a self-review..."
    _PROMPT_V2,   # "Before this PR is reviewed..."
    _PROMPT_V3,   # "Stop. Before opening the PR..."
]

def _select_variation(ctx) -> int:
    seed = hash((ctx.project_id, ctx.session_id))
    return seed % len(_FOUR_LENS_PROMPT_VARIATIONS)
```

Variations need not differ in *content* — the four lenses are the
four lenses. They differ in framing, ordering, and emphasis enough
that pre-reading "the" tripwire prompt no longer maps cleanly to
what the agent receives.

This is over-engineering for the canonical case; it earns its
keep when project teams add their own tripwires and want to
prevent agents from optimising against them.

## 6. Acknowledgement mechanism

When a tripwire's `blocks=True` and the agent calls the firing
command:

1. **First call** (no marker exists):
   - Command does NOT perform its normal action
   - Command stdout returns the tripwire payload (verbatim text)
   - Command exit code is 1 (so wrappers can detect)
   - The agent reads the stdout as if it were any other CLI output
2. **Agent acts** on the tripwire instructions
3. **Agent re-calls** the same command with `--ack`:
   - `tripwire session complete <id> --ack`
   - This writes the marker at
     `.tripwire/acks/<tripwire-id>-<session-id>.json`
   - The marker contains: agent's PR comment URL or commit SHA(s) of
     the fix commits, plus a free-form `notes` field
4. **Second call** (marker exists):
   - `is_acknowledged()` returns True
   - Command performs its normal action

Agents are instructed in their launch prompt: "if `tripwire session
complete` returns instructions, treat them as a fresh task. When
done, re-run with `--ack`."

The `--ack` flag is the agent's explicit signal "I have addressed
the response I just received." Without it, the agent could re-run
the command and the tripwire would fire again — agents *could* get
into a loop, but then `--ack` is the documented escape, learned
once.

### 6.1 Why marker files vs in-memory state

Marker files survive process restarts, CI re-engagement, and human
intervention. They're auditable. They're discoverable by `git
status` if accidentally committed (preventable via `.gitignore` on
`.tripwire/acks/`).

The marker is per-(tripwire, session). A second self-review
tripwire firing on the same session in a re-engagement after CI
failure would not block (already acknowledged). This is correct —
the agent shouldn't be re-tripped on every retry. Future: a
`--reset-acks` for cases where the original work was substantially
redone.

## 7. Visibility model

The asymmetric visibility is the whole point.

| Audience | What they see |
|---|---|
| **Executing agent** | Tripwire content only when fired. Cannot list registered tripwires, cannot inspect manifest, cannot read `_internal/tripwires/` via skill-loaded surfaces. |
| **PM agent / human reviewer** | `tripwire session log <id>` shows all tripwires that fired for that session, when, the prompt delivered, the agent's response (PR comment URL + commits referenced in the marker). |
| **Project administrator** | `tripwire tripwires list` (PM-only command) shows registered tripwires + projects they apply to. Tripwire content only revealed via `--reveal` flag with a confirmation prompt. |

Implementation: the PM-side `tripwires list` and `session log`
commands live in `tripwire/cli/admin.py` (or similar) and are gated
by a project-level role marker (e.g., `~/.tripwire/role: pm`)
defaulting to "executor" for safety. Executor-mode CLIs simply
don't have the subcommands.

Reality check: this isn't strong access control. An agent running
on the PM's machine inherits PM role. The model is closer to
"semantic separation by role" than "security boundary." The
gameability mitigation is module hiding (§5) plus prompt
variations (§5.1), not access control.

## 8. The canonical first tripwire — self-review

Spec for the four-lens self-review tripwire that ships with v0.8:

```python
# src/tripwire/_internal/tripwires/self_review.py

class SelfReviewTripwire(Tripwire):
    id = "self-review"
    fires_on = "session.complete"
    blocks = True

    def fire(self, ctx: TripwireContext) -> str:
        return _select_variation(ctx, _VARIATIONS)

    def is_acknowledged(self, ctx: TripwireContext) -> bool:
        marker = ctx.ack_path("self-review")
        return marker.is_file() and self._marker_substantive(marker)

    @staticmethod
    def _marker_substantive(marker_path: Path) -> bool:
        """The agent's --ack must reference at least one fix commit
        OR explicitly state 'no findings, all four lenses walked'."""
        data = json.loads(marker_path.read_text())
        return bool(data.get("fix_commits") or data.get("declared_no_findings"))
```

The four-lens prompt content (three variations) lives next to the
class. See the canonical prompt in the conversation log dated
2026-04-21 — explicitly **NOT** copied here in the spec, because
this spec ITSELF is in the agent's read-path. The implementation
PR will land the prompt content in `_internal/` only.

## 9. Future tripwires (v0.8.x backlog)

Each is a small additive PR after the primitive lands.

| Tripwire | Fires on | What it asks |
|---|---|---|
| **AC substantiation** | `issue close` | Pick one acceptance criterion at random; agent must point to file:line evidence. |
| **Security trace** | `pr open` | Pick one untrusted input from the diff; agent must trace it to a sanitiser/validator. |
| **Cite-this-claim** | `validate run` (when developer.md exists) | Pick one claim from the agent's developer.md (e.g., "thread-safe"); demand evidence. |
| **Re-engagement diff** | `session resume` after CI fail | "What's different now vs your last attempt? What assumption broke?" |
| **Fatigue calibration** (deferred) | Token threshold mid-session | "Compare your last commit to your first. Are you maintaining the same depth?" |

Project teams can add their own tripwires by registering modules in
`project.yaml`:

```yaml
tripwires:
  enabled: true                # global on/off (default: true)
  opt_out: []                  # session ids to skip ALL tripwires (rare)
  extra:
    - id: my-team-pii-check
      fires_on: pr.open
      module: ./tripwires/pii_check.py    # project-local Python module
```

## 10. Schema additions

### 10.1 `project.yaml`

```yaml
tripwires:
  enabled: true                 # default true
  opt_out: []                   # session ids
  extra: []                     # list of {id, fires_on, module}
```

### 10.2 `session.yaml`

No new fields. Tripwires apply universally; session opt-out lives
at the project level (intentional — making opt-out per-session
visible in session.yaml would let the agent see "no tripwires here,
phew").

### 10.3 `templates/manifest.yaml`

Unchanged. Tripwires are not artifacts; the artifact manifest
remains the source of truth for produced files. A tripwire MAY
require an artifact as part of its acknowledgement (e.g.,
self-review requires a PR comment), but the artifact is the means;
the tripwire is the gate.

## 11. Migration path

v0.8 can ship the primitive without breaking v0.7b. Steps:

1. **v0.8.0** — primitive infrastructure: base class, registry,
   marker files, ack flag, PM-side log command. Ships with **zero**
   built-in tripwires registered. Existing CLI commands behave
   unchanged.
2. **v0.8.1** — register the self-review tripwire on
   `session.complete`. This is a behaviour change for execution
   agents, but the change is exactly the desired one.
3. **v0.8.2+** — additional tripwires from §9 backlog, one per
   release.

Each release is small. Behaviour changes are gated by the
infrastructure already shipped, so users can opt out at the project
level if they need to.

### 11.1 Project opt-out

```yaml
# project.yaml
tripwires:
  enabled: false   # disables ALL tripwires for this project
```

Useful for:
- Test projects (don't want noise during keel-testing-keel)
- Projects whose agents are specifically being benchmarked without
  tripwires

The opt-out lives in `project.yaml` so agents reading their own
project can in principle see whether tripwires are off — that's
fine, it's not security-relevant info.

## 12. Out of scope (for v0.8)

- **Threshold-based tripwires** (token/turn count mid-session).
  Requires spawn-wrapper integration for stream-json events.
  Land in v0.9.
- **Cross-session tripwires.** A tripwire that fires on PM-side
  `session merge` looking at the diff between two sessions. v0.9+.
- **Adversarial tripwires.** Auto-generated tripwires that adapt
  to a specific agent's gaming pattern. Research direction; not
  v0.8.
- **Tripwire metrics.** "What % of sessions had self-review
  findings?" Useful but not load-bearing for the primitive itself.

## 13. Open questions

- **What if the agent ignores the tripwire and just `gh pr create`s
  directly?** Today, nothing forces them through `tripwire session
  complete`. v0.8 should add a session-state check on PR creation:
  `gh pr create` from a session worktree without `session complete`
  having succeeded blocks via a pre-push hook. That hook lives in
  the worktree's `.git/hooks/pre-push` and is set up by `session
  spawn`. Open: should pre-push enforcement be on by default, or
  opt-in?
- **What about `--ack` being too easy?** The agent could just
  `--ack` immediately without acting. Mitigation: marker file
  validation — the marker must contain at least one fix commit SHA
  or an explicit `declared_no_findings: true`. Could go further:
  PM-side log entry shows the marker contents, easy audit. Lean:
  keep it simple, audit-after rather than enforce-during.
- **Should tripwires be testable?** Yes — `tripwire test-tripwire
  <id>` is a PM-only command that fires the tripwire prompt
  manually for inspection. Useful when authoring new tripwires.
- **How do we handle the agent that gets stuck in a tripwire loop?**
  E.g., re-runs `session complete` repeatedly, gets the prompt each
  time, never `--ack`s. Add a turn-count safety: after 3 fires of
  the same tripwire on the same session, escalate to a hard error
  with a message pointing the agent at `--ack`.
- **Documentation for executors.** They need to know `--ack` exists
  without us spelling out what tripwires are. The launch prompt
  template gets a generic line: "Some commands may return
  additional instructions instead of confirming. Treat those as
  fresh tasks; re-run the command with `--ack` after acting on
  them." That's enough orientation without revealing tripwire
  content.

## 14. Effort estimate

| Component | Estimate |
|---|---|
| `Tripwire` base class + registry + manifest loader | 1 day |
| Marker file + `--ack` flag plumbing | 0.5 day |
| Hook into `tripwire session complete` (v0.7b Phase 6 dependency) | 0.5 day |
| `_internal/` package layout + import hygiene tests | 0.5 day |
| Self-review tripwire (3 variations, marker validation) | 1 day |
| PM-side `tripwire session log <id>` | 1 day |
| PM-side `tripwire tripwires list [--reveal]` | 0.5 day |
| Pre-push hook for worktree (gh pr create gate) | 1 day |
| Project opt-out + `project.yaml` schema | 0.5 day |
| Tests (registry, ack flow, hook firing, opt-out) | 2 days |
| **Subtotal — primitive** | **~8.5 days** |
| Each additional tripwire (AC substantiate, security trace, etc.) | 0.5–1 day |

## 15. Testing strategy

| Test | Verifies |
|---|---|
| `test_registry_loads_manifest` | Manifest YAML parses; classes resolve |
| `test_tripwire_fires_on_event` | First call returns prompt + exits 1 |
| `test_ack_flag_writes_marker` | `--ack` creates the marker JSON |
| `test_second_call_after_ack_succeeds` | After marker, command performs normal action |
| `test_marker_requires_substance` | Empty `--ack` rejected; needs commit SHAs or declared_no_findings |
| `test_loop_safety` | 3rd fire on same session escalates to hard error |
| `test_opt_out_disables_all` | Project with `enabled: false` skips tripwires |
| `test_pm_log_shows_fires` | `session log` displays all tripwire fires + responses |
| `test_internal_not_in_skill_loadpath` | Skill loader does not see `_internal/tripwires/*` content |
| `test_variations_pick_deterministically` | Same (project, session) seeds same variation |

## 16. Cross-references

- `2026-04-17-v07-issue-developer-notes.md` — the per-issue
  artifacts spec; the AC-substantiate tripwire (§9) reads issue
  developer.md for evidence
- `2026-04-16-v07-pm-monitor.md` — `pm-session-complete` is the
  hook point for `session.complete` events
- `2026-04-20-v07-unified.md` — v0.7's existing primitives;
  this spec adds the third
- `src/tripwire/templates/skills/project-manager/references/ANTI_PATTERNS.md`
  — the fatigue / quality-degradation pattern this primitive
  systematically counters
- `V0.8-RAW.MD` item 4 — the original raw note this spec expands
- Conversation log 2026-04-21 — the brainstorm that produced both
  the four-lens prompt and the primitive insight
