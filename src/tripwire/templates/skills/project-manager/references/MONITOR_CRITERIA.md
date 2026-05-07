# Monitor Criteria

The `pm-monitor` workflow runs an overseer loop —
`scan → classify → dispatch → idle → scan` — periodically inspecting
project state (sessions, PRs, inbox, comments, nodes) and emitting
**signals**. Each signal maps to a dispatch target — a status in
another workflow the PM either runs inline or spawns as a Claude Code
subagent. The loop turns one-shot commands into continuous oversight.

## Signal vocabulary

| Column | Meaning |
|---|---|
| Source | where the predicate reads from |
| Threshold | when the signal fires |
| Dispatch | cross-link target the `dispatch` station routes to |

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

Thresholds live in `project.yaml` under `monitor:` so tuning doesn't
need code edits:

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

`tick_seconds` paces `idle → scan`. `session_crash` requires both
staleness AND silence. `no_human_reply_minutes` is the patience window
for blocking agent messages before escalation.
`stale_node_count_high` is when freshness graduates from per-node to
project-wide. `workflow_drift.min_severity` filters drift events —
informational entries log but don't dispatch.

## Dispatch contract

Each signal fires one route from `classify` into `dispatch`; the
target workflow rides on `dispatch`'s outgoing cross-links. Two modes
per cross-link:

- **Inline** (`pm_subagent_dispatch: false`) — PM walks the target
  workflow in its own context. For full-context judgment (escalation,
  phase advancement).
- **Subagent** (`pm_subagent_dispatch: true`) — PM spawns a Claude
  Code subagent scoped to the target workflow with the signal
  payload (entity uuids) and a system prompt restricting it to that
  workflow's allowable operations. Returns a structured summary into
  the audit trail.

Multiple signals can fire on one scan; PM dispatches in declaration
order (session lifecycle → inbox/comment → freshness/drift → idle).

## Audit trail

Every fire/dispatch appends to
`<project>/orchestration/monitor-log.yaml`:

- `signal_id`, `entity_uuids` (matched sessions/issues/nodes)
- `dispatched_to` (`workflow.status`), `mode` (`inline`|`subagent`)
- `subagent_summary` (subagent return payload)
- `started_at` / `ended_at` (tick timing)

Canonical record of what the overseer did and why — the artifact the
user reads to reconstruct overnight history.

## Cross-references

- `SUBAGENT_DELEGATION.md` — subagent dispatch protocol (input
  payload, scope token, return contract). Until the pm-monitor
  sections land there, treat this file as the authoritative
  description of the dispatch contract.
- `WORKFLOWS_CODE_REVIEW.md` — target for `signal.session_pr_pair_open`.
- `WORKFLOWS_TRIAGE.md` — target for `signal.inbox_inbound_new` and
  `signal.comment_question`.
- `nodes/pm-monitor-loop.yaml` — concept node for the loop itself.

## Tuning

The values above are starting points, not calibrated. Edit
`monitor:` in `project.yaml` when a signal fires too often (noise),
too rarely (missed escalations), or dispatches wrong. Document the
change in `templates/orchestration/monitor-log.yaml`.

Adding a new signal is a workflow.yaml change, not a threshold tweak.
Required: (1) new entry in the table; (2) a route in `pm-monitor`
from `classify → dispatch` keyed on the signal; (3) a cross-link from
`dispatch` to the target status; (4) runtime predicate code (Stage 2).

Signal IDs appear in the audit log and workflow.yaml — treat the
vocabulary as ABI-stable. Removing one is a breaking change.
