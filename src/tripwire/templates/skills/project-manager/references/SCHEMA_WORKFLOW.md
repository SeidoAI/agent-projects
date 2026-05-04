# Schema: workflow.yaml

Per-project workflow definitions live at `workflow.yaml` in the
project root. Each workflow is a typed lifecycle graph: status
territory, routed transitions, declared artifacts, controls, and
cross-links to sibling workflows. The runtime parses it into the
dataclass tree at `src/tripwire/core/workflow/schema.py` — that
module is the authoritative shape; this doc is the user-facing
reference.

## Four-primitive control vocabulary

Every gate or check on a status or route is exactly one of these
four primitives. Adding a fifth requires a schema change, not a
config tweak.

| Primitive | Semantics |
|---|---|
| `tripwire` | Hard pass/fail gate. Failure halts the route. |
| `heuristic` | Soft warn-once detector. Surfaces in validate output, does not block. |
| `jit_prompt` | Hidden ack-required prompt. Loads when the route fires; needs explicit ack to advance. |
| `prompt_check` | Required slash-command invocation. Audits that the named command was actually run. |

Canonical definitions are the four concept nodes:
`tripwire-primitive`, `heuristic-primitive`, `jit-prompt-primitive`,
`prompt-check-primitive`.

## Top-level shape

```yaml
workflows:
  <workflow-id>:
    actor: <actor-name>            # e.g. pm-agent, coding-agent
    trigger: <event-name>          # spawning event
    brief-description: "..."
    statuses: [...]
    routes: [...]
```

## Status entry

A status is a node in the lifecycle graph. The entity sits there
until a route advances it.

```yaml
- id: executing
  next: in_review                  # single id
  # OR:
  next:                            # conditional, equality-only
    - if: gaps.present == true
      then: draft
    - else: publish
  # OR:
  terminal: true                   # no next

  prompt_checks: [<id>, ...]
  tripwires:    [<id>, ...]
  heuristics:   [<id>, ...]
  jit_prompts:  [<id>, ...]

  artifacts:
    consumes:
      - id: plan
        label: plan.md
    produces:
      - id: diff
        label: implementation diff
        path: sessions/{session_id}/artifacts/diff.md   # optional

  work_steps:                      # work *inside* the status
    - id: implement
      actor: coding-agent
      label: implement
      skills: [backend-development, agent-messaging]

  cross_links:
    - workflow: pr-lifecycle
      status: draft
      kind: triggers
      label: PRs opened mid-session
```

Conditional `next` predicates are equality-only for v0.9
(`<dot-path> (==|!=) <bare-value>`). The dot-path resolves against
the workflow context.

`work_steps` describe the actor's labour while in the status. They do
not change status — routes do.

## Route entry

A route is a transition between statuses (or between a boundary port
and a status). Controls on the route fire on traversal.

```yaml
- id: queued-to-executing
  actor: pm-agent
  command: pm-session-spawn        # optional, command-driven routes
  trigger: command.pm-session-spawn
  from: queued                     # status id OR source:<port>
  to:   executing                  # status id OR sink:<port>
  kind: forward                    # forward | return | loop | side | terminal
  label: spawn coding agent
  signals: [signal.session_unblocked]
  controls:
    tripwires:    [<id>, ...]
    heuristics:   [<id>, ...]
    jit_prompts:  [<id>, ...]
    prompt_checks: [<id>, ...]
  skills: [project-manager, backend-development]
  emits:
    artifacts: [<artifact-ref>, ...]
    events:    [<event-name>, ...]
    comments:  [<comment-kind>, ...]
```

`kind` semantics: `forward` advances; `return` goes back (e.g. review
requesting changes); `loop` is a self-edge or short-cycle; `side`
branches without forward progress (e.g. paused); `terminal` exits to
a sink port.

`signals` wires `pm-monitor` predicates to this route. Full vocabulary
in `MONITOR_CRITERIA.md`.

## Cross-links

A cross-link declares that a status hands off to (or is handed off
from) a status in another workflow. The renderer draws from the
`triggers` side; `triggered_by` entries are advisory.

```yaml
cross_links:
  - workflow: code-review
    status: received
    kind: triggers                 # triggers | triggered_by
    label: review takes ownership
    pm_subagent_dispatch: true
```

`pm_subagent_dispatch: true` flags that the dispatched workflow runs
inside a Claude Code subagent (Task-style spawn) rather than the
parent PM agent's session. Contract — input payload, scope, return
summary — is in `SUBAGENT_DELEGATION.md`.

## Boundary ports

Routes can connect statuses to external ports:

- `source:<name>` — entry port (e.g. `source:issue`).
- `sink:<name>` — exit port (e.g. `sink:main`).

Boundary ports declare no controls or work_steps. The status on the
other side of the edge owns them.

## Validation

`tripwire validate` parses `workflow.yaml` and runs well-formedness
checks. Failure modes:

- `workflow/duplicate_status_id`
- `workflow/unknown_next_status`
- `workflow/terminal_with_next`
- `workflow/no_terminal_status` — every workflow must converge.
- `workflow/unknown_tripwire`, `workflow/unknown_heuristic`,
  `workflow/unknown_jit_prompt`, `workflow/unknown_prompt_check`

See `VALIDATION.md` for the full error catalogue.

## See also

- `VALIDATION.md` — error catalogue and exit codes.
- `MONITOR_CRITERIA.md` — signal vocabulary and dispatch contract.
- `WORKFLOWS_CODE_REVIEW.md` — canonical multi-status workflow.
- `SUBAGENT_DELEGATION.md` — `pm_subagent_dispatch` contract.
