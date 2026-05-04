# Monitor Criteria

The signal vocabulary the `pm-monitor` workflow uses to decide what
to do next. The PM agent runs an overseer loop — `scan → classify →
dispatch → idle → scan` — that periodically inspects project state
(sessions, PRs, inbox, comments, nodes) and emits one or more
**signals**. Each signal maps to a downstream dispatch target: a
specific status in another workflow that the PM either runs inline or
spawns as a Claude Code subagent. Without this loop the PM is a
one-shot command per request; with it the PM has continuous oversight
without human prompting.

## Signal vocabulary

The full table of v0.9 signals. Source = where the predicate reads
from. Threshold = the condition that fires the signal. Dispatch =
the cross-link target the `dispatch` station routes the signal to.

| Signal | Source | Threshold | Dispatch |
|---|---|---|---|
| `signal.session_unblocked` | sessions/*/session.yaml + graph cache | all `blocked_by_sessions` in {completed, done, verified} | coding-session.queued |
| `signal.session_crashed` | runtime_state.engagements + heartbeat log | last_engagement.ended_at + 15m < now AND no heartbeat in 5m window | coding-session.executing (relaunch) |
| `signal.session_paused_question` | agent-messaging log | last msg type ∈ {question, plan_approval, stuck, escalation, handover} AND priority=blocking AND no human reply within 10m | inbox-handling (escalate) OR pm-incremental-update |
| `signal.session_pr_pair_open` | session.yaml + gh PR API | both `tripwire-pr` and `project-pr` set, both PRs in {open, ready_for_review} | code-review.received |
| `signal.inbox_inbound_new` | filesystem walk | inbox/*.md with resolved=false AND not yet processed | pm-triage.intake |
| `signal.comment_question` | issues/*/comments/*.yaml mtime | recent comment type=question AND no reply | pm-triage.intake |
| `signal.workflow_drift_detected` | events log + workflow.yaml | drift detection rules return non-empty | inbox-handling (FYI bucket) |
| `signal.stale_node_count_high` | nodes/ + content_hash check | count of `v_freshness` failures >= 5 | concept-freshness.detected |
| `signal.nothing_to_do` | self-test | no other signal predicate holds | pm-monitor.idle |

## Threshold configuration

Thresholds live in `project.yaml` under a `monitor:` block so iteration
doesn't require code edits. Initial values:

```yaml
monitor:
  tick_seconds: 60
  session_crash:
    stale_engagement_minutes: 15
    no_heartbeat_minutes: 5
  session_paused_question:
    no_human_reply_minutes: 10
  stale_node_count_high: 5
  workflow_drift:
    min_severity: warning
```

`tick_seconds` controls how often the `idle → scan` route fires.
The `session_crash` thresholds together define a "crashed" engagement
(stale enough AND silent enough). `no_human_reply_minutes` is the
patience window for blocking agent messages before escalation. The
`stale_node_count_high` threshold determines when concept-freshness
graduates from a per-node concern to a project-wide one.

`workflow_drift.min_severity` filters drift events: only warnings and
errors fire `signal.workflow_drift_detected`; informational drift
entries are recorded but do not dispatch.

## Dispatch contract

Each signal fires exactly one route from `pm-monitor.classify` into
`pm-monitor.dispatch`. The route's `to` is always `dispatch`; the
target workflow is encoded on `dispatch`'s outgoing cross-links.

Dispatch is one of two modes per cross-link:

- **Inline** — `pm_subagent_dispatch: false`. The PM acts in its
  own context, opening the target workflow and walking it. Used when
  the dispatch requires PM full-context judgment (e.g. escalating to
  a human, advancing a phase).
- **Subagent** — `pm_subagent_dispatch: true`. The PM spawns a
  Claude Code subagent scoped to the target workflow. The subagent
  receives the signal payload (matched entity uuids) and a system
  prompt restricting it to that workflow's allowable operations. It
  returns a structured summary the PM records in the audit trail.

Multiple signals may fire on the same scan. The PM dispatches in
declaration order — typically session lifecycle signals first, then
inbox/comment signals, then concept-freshness and drift, then idle.
A single scan can trigger multiple dispatches.

## Audit trail

Every fire/dispatch pair appends an entry to
`<project>/orchestration/monitor-log.yaml`. The entry records:

- `signal_id` — the signal that fired
- `entity_uuids` — the matched entities (sessions, issues, nodes)
- `dispatched_to` — the cross-link target (`workflow.status`)
- `mode` — `inline` or `subagent`
- `subagent_summary` — for subagent dispatches, the structured
  return payload from the spawned task
- `started_at` / `ended_at` — timing for tick reconstruction

The audit log is the canonical record of what the overseer did and
why. It's the artifact the user reads to understand a session's
overnight history.

## Cross-references

- `SUBAGENT_DELEGATION.md` — the Claude Code subagent dispatch
  protocol used when `pm_subagent_dispatch: true`. Specifies input
  payload, scope token, and return contract. Note: the pm-monitor
  sections of that doc land in a follow-up commit; until then,
  treat this file as the authoritative description of the dispatch
  contract.
- `WORKFLOWS_CODE_REVIEW.md` — destination workflow for
  `signal.session_pr_pair_open`.
- `WORKFLOWS_TRIAGE.md` — destination workflow for
  `signal.inbox_inbound_new` and `signal.comment_question`.
- `nodes/pm-monitor-loop.yaml` — the concept node documenting the
  overseer loop itself.

## Tuning the thresholds

The values in this document are **starting values**. They are not
calibrated to any specific project's cadence. The user explicitly
chose to ship with sensible defaults and iterate by observation. As
soon as you see a signal that fires too often (noise), too rarely
(missed escalations), or with the wrong dispatch (wrong workflow
opened), edit the `monitor:` block in `project.yaml` and document
the change in `orchestration/monitor-log.yaml` so the diff is
auditable.

If you find yourself wanting to add a new signal — a predicate the
existing nine don't cover — that's a workflow.yaml change, not a
threshold tweak. New signals require:

1. A new entry in this table
2. A route in `pm-monitor` from `classify → dispatch` keyed on the
   new signal
3. A cross-link from `dispatch` to the target workflow's status
4. Predicate evaluation code in the runtime (Stage 2 work)

Treat the signal vocabulary as expandable but ABI-stable: signal ids
appear in the audit log and in workflow.yaml, so removing one is a
breaking change.
