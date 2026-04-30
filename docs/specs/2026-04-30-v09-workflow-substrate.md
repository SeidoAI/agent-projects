# v0.9 — Workflow primitive (substrate)

**2026-04-30**

This is the design spec for the v0.9 workflow primitive: a per-project
`workflow.yaml` that hosts every lifecycle, station-registered
validators / tripwires / prompt-checks, transition-token runtime, an
append-only events log, and workflow-drift detection. Inherits all
locked decisions from `backlog-architecture.md`.

## What changes vs v0.8

Before v0.9, the lifecycle was implicit in PM-skill markdown,
validator hooks, tripwire registration code, slash command shells, the
`project.yaml` lifecycle enum, and `enums/issue_status.yaml`. No
single document said what the process looked like end-to-end.

After v0.9, the lifecycle is one file: `<project>/workflow.yaml`. It
declares stations, gate predicates, and every check/tripwire/prompt
that runs at each station. The runtime drives state transitions
through the gate; the events log records everything; the drift report
flags mismatches.

## Schema

```yaml
workflows:
  <workflow-id>:
    actor: <actor-name>            # e.g. coding-agent
    trigger: <event-name>          # e.g. session.spawn
    stations:
      - id: <station-id>
        # one of:
        next: <station-id>                    # single
        next:                                 # conditional
          - if: <field> == <value>
            then: <station-id>
          - else: <station-id>                # default branch
        terminal: true                        # terminal station

        prompt_checks: [<id>, ...]            # optional
        validators: [<id>, ...]               # optional
        tripwires: [<id>, ...]                # optional
```

### Conditional predicates

Equality only for v0.9 (`==`, `!=`). The LHS is a dot-path into the
workflow context (e.g. `agent.role`, `session.kind`). The RHS is a
bare token treated as a string literal. No conjunctions, no
comparisons, no membership tests — add operators only when a real
workflow needs them.

### Multiple workflows per file

The schema supports multiple workflows in one file. v0.9 ships only
`coding-session`. v1.0 adds `inbox-handling`, `issue-lifecycle`,
`concept-freshness`, `pr-lifecycle`.

## Well-formedness

`tripwire validate` runs the workflow well-formedness validator. It
catches:

| Code | Meaning |
|------|---------|
| `workflow/duplicate_station_id` | Two stations share an id |
| `workflow/unknown_next_station` | `next:` references an undeclared station |
| `workflow/terminal_with_next` | A station marks `terminal: true` AND declares `next:` |
| `workflow/no_terminal_station` | A workflow has no terminal station |
| `workflow/missing_next_or_terminal` | A station declares neither |
| `workflow/invalid_predicate` | A conditional `if:` is malformed |
| `workflow/invalid_next_shape` | `next:` is neither a string nor a list |
| `workflow/unknown_validator` | A station references an unregistered validator |
| `workflow/unknown_tripwire` | A station references an unregistered tripwire |
| `workflow/unknown_prompt_check` | A station references an unregistered prompt-check |

## Station registration

Each existing validator declares its station via metadata:

```python
@registers_at("coding-session", "executing")
def check_uuid_present(ctx): ...
```

Each Tripwire subclass declares its station via a class attribute:

```python
class SelfReviewTripwire(Tripwire):
    at: ClassVar[tuple[str, str]] = ("coding-session", "review")
```

Each PM-skill slash command declares it via frontmatter:

```yaml
---
name: pm-session-review
fires_at: review
---
```

The registry indexes these and the gate runner looks them up at
transition time.

## Events log

Append-only JSON-Lines under `<project>/events/`. One file per UTC
date (`events/2026-04-30.jsonl`). Schema:

```json
{
  "ts": "2026-04-30T15:00:00Z",
  "workflow": "coding-session",
  "instance": "v09-workflow-substrate",
  "station": "executing",
  "event": "validator.run",
  "details": { "id": "v_uuid_present", "outcome": "pass" }
}
```

All emission flows through one `emit_event(...)` function. Validators,
tripwires, and transitions all use it. The log is append-forever — no
rotation in v0.9.

## Transition runtime

`tripwire transition <session-id> <to-station>` submits a transition
request:

1. Load workflow.yaml, look up validators / tripwires / required
   prompt-checks for `<to-station>`.
2. Acquire `.tripwire/locks/transition-<sid>.lock` to serialise
   concurrent calls on the same session.
3. Run the gate (validators → tripwires → prompt-checks).
4. On pass: update session.yaml's status, emit
   `transition.completed`.
5. On fail: emit `transition.rejected` with `reason`. Session stays
   at the current station.

The validator step reuses the KUI-110 edit-time hook surface — the
gate calls `validate_project(...)` directly, the same code path the
PostToolUse hook drives.

## Drift detection

`tripwire drift report` queries the events log for:

- Missing required prompt-checks at a station the session passed
  through
- Unexpected transitions (gate-bypass writes that flip session.yaml
  status without going through `tripwire transition`)
- Tripwires that should-have-fired-but-didn't per the workflow.yaml
  declaration

Empty on a clean run; correct mismatches surfaced when steps are
skipped.

## What's deferred

- Schema versioning (`_schema_version` + `tripwire migrate`) — v1.0.
- Additional workflows in workflow.yaml — v1.0.
- Concrete deviation tripwires — `v09-entity-graph-consumers`.
- Lint expansion — `v09-validators-tripwires-authoring`.
- Tripwire authoring loop — same.
- Workflow Map UI — `v09-workflow-consumers-ui`.
