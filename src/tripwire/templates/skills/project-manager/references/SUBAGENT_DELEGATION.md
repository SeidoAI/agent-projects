# Subagent delegation

The PM agent dispatches Claude Code subagents during
`pm-monitor.dispatch` when a cross-link in `workflow.yaml` carries
`pm_subagent_dispatch: true`. This document codifies that contract.

The general "don't delegate entity writes to subagents" rule in
`SKILL.md` still holds. This protocol is narrower: the dispatched
subagent is **scoped to one workflow's allowable operations**, not
free-form file generation. The parent PM still owns the audit trail.

## When the PM dispatches a subagent

The PM acts as a conductor. On every tick, `pm-monitor.scan` collects
state and `pm-monitor.classify` emits one or more signals (vocabulary
in `MONITOR_CRITERIA.md`). Each signal maps to a cross-link out of
`pm-monitor.dispatch`. When that cross-link has
`pm_subagent_dispatch: true`, the PM spawns a subagent rather than
walking the target workflow inline.

## Input payload

The PM hands the subagent:

- **Workflow id + target status** — the cross-link target (e.g.
  `code-review.received`).
- **Signal payload** — the entity uuids that matched the predicate
  and a one-paragraph evidence summary the PM extracted from `scan`.
- **Scoped task description** — "advance this entity through this
  workflow"; not free-form. The workflow's status declares the
  artifacts and controls.
- **Audit-trail pointer** — the path to the
  `<project>/orchestration/monitor-log.yaml` entry the PM has just
  appended for this dispatch. The subagent appends its return
  summary to that entry on exit.

## Subagent scope

The subagent's system prompt restricts it to the dispatched workflow.
The "no subagents for entity writing" rule is preserved by making the
dispatched subagent **scoped to one workflow's operations** — not
free-form delegation.

The subagent's prompt names exactly one workflow id and forbids:

- Opening any other workflow.
- Writing files outside the artifacts that workflow's statuses
  declare under `produces:`.
- Spawning further subagents (no recursion).
- Modifying `workflow.yaml`, `project.yaml`, or any enum file.

The subagent runs `tripwire validate` before returning; if validate
fails on its own writes, it must repair before exit.

## Return summary

The subagent emits a structured summary on exit. The PM appends it
to the matching entry in `monitor-log.yaml`:

```yaml
subagent_summary:
  workflow: code-review
  status: received          # status the subagent owned on exit
  artifacts:
    - sessions/<id>/reviews/synthesis.md
  outcome: success           # success | partial | failed
  reason: >
    Three reviewers returned, synthesis written, verdict=merge.
```

`outcome` enum:

- **`success`** — advanced to the next status (or terminal) and
  wrote every required artifact.
- **`partial`** — made progress but did not reach a hand-off-ready
  state. The PM decides whether to re-dispatch or escalate.
- **`failed`** — could not advance. The PM opens an inbox item.

`reason` is one paragraph of plain text. The artifacts list points
at the actual writes.

## Allowed dispatched workflows

ALLOWED:

- **`code-review`** — `independent-reviews` station for the
  superpowers reviewer specifically; full workflow for the relaunch
  path.
- **`pm-triage`** — full workflow. Inbox intake and classification.
- **`pm-incremental-update`** — full workflow. Small atomic edits
  to existing entities.

NOT ALLOWED:

- **`pm-scoping`** — requires PM full-context judgment per plan §9.
- **`phase-advancement`** — requires PM full-context judgment per
  plan §9.
- **`pm-monitor`** itself — recursion. Subagents must not spawn
  further subagents.

## See also

- `WORKFLOWS_CODE_REVIEW.md` — canonical multi-reviewer workflow.
- `MONITOR_CRITERIA.md` — signal vocabulary and dispatch contract.
- `nodes/pm-monitor-loop.yaml` — the overseer pattern as a node.
