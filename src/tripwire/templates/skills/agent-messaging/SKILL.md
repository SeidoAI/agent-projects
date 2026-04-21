---
name: agent-messaging
description: >-
  How to communicate with the human operator (and other agents) via the
  MCP messaging server. Covers when to send each message type, priority
  semantics, the mandatory status heartbeat, and anti-patterns. Loaded
  by default into every agent-containers session regardless of agent
  type — all agents in containerised execution need this.
license: MIT
metadata:
  author: tripwire
  version: "1.0"
compatibility: >-
  Agents running in agent-containers with the MCP agent-messaging server
  mounted. The server exposes `send_message` and `check_messages` tools.
---

# Agent Messaging

You have an MCP server named `agent-messaging` mounted in your container.
It exposes two tools:

- **`send_message`** — post a message to the human operator via the
  project dashboard
- **`check_messages`** — read any pending responses to your messages

Use it to coordinate with the human in real time. Messages are NOT
committed to git as they happen — they are ephemeral. When your session
completes, the full message log is persisted to
`sessions/<id>/messages.yaml` in the project repo.

## When you MUST send a message

These are non-negotiable. Skipping them breaks the orchestration flow.

### Status heartbeat (every ~5 minutes of active work)

Every 5 minutes of active work, send a `status` message so the UI and
the PM agent can see what you're doing. Status messages have a
structured body: `{state, summary}` where:

- `state` is one of the values in `<project>/enums/agent_state.yaml`
  (investigating, planning, awaiting_plan_approval, implementing,
  testing, debugging, refactoring, documenting, self_verifying,
  blocked, handed_off, done)
- `summary` is 1-2 plain-text sentences

Always `informational` priority — status messages never block.

Example:
```json
{
  "type": "status",
  "priority": "informational",
  "body": {
    "state": "implementing",
    "summary": "Wired the JWT middleware into the auth router. Now writing unit tests for the validation logic."
  }
}
```

Send a status message on every state transition too (e.g. moving from
`investigating` → `planning`, or from `implementing` → `testing`).

### Plan approval (if the project requires it)

Check `<project>/templates/artifacts/manifest.yaml`: if the `plan`
artifact has `approval_gate: true`, you MUST send a `plan_approval`
message after writing `plan.md` and before starting implementation:

```json
{
  "type": "plan_approval",
  "priority": "blocking",
  "body": "## My plan\n\n(the contents of plan.md)..."
}
```

Then **stop and exit**. The orchestrator will re-engage you with the
human's response via `check_messages`.

### Blocking questions (when you can't proceed)

If you have a genuine ambiguity that blocks correct work, send a
`question` message with `priority: blocking` and stop:

```json
{
  "type": "question",
  "priority": "blocking",
  "body": "Should `/auth/refresh` rotate the refresh token or keep the same one? The contract in [[contract-auth-token]] doesn't specify. Option A: rotate (safer, more complex). Option B: reuse (simpler, less safe). I lean toward A unless you disagree."
}
```

Good blocking questions:
- Have specific options, not just "what should I do?"
- Reference the ambiguous source (a node, a doc, a conflicting rule)
- Include your preferred answer with reasoning

## When you MAY send a message

### Progress updates (`informational`)

Milestones worth surfacing but not blocking work. Keep going after
sending:

```json
{
  "type": "progress",
  "priority": "informational",
  "body": "Unit tests passing. Moving to integration tests now."
}
```

### FYI (`informational`)

Things you discovered that are interesting but outside your scope:

```json
{
  "type": "fyi",
  "priority": "informational",
  "body": "Found an unrelated bug in [[user-model]].find_by_email — it catches all exceptions instead of NotFound. Not touching it in this issue but worth a follow-up."
}
```

## When you MUST stop after sending

These messages are `blocking` — sending them means your work is
paused until a human responds:

- `plan_approval` — waiting for approval to start implementation
- `question` — needs an answer before you can proceed
- `stuck` — tried 3+ approaches, genuinely can't make progress
- `escalation` — need elevated permissions or scope change
- `handover` — passing the work to a human; don't expect a response

After sending any of these, exit your agent loop. The orchestrator
will re-engage you with the response when one arrives.

## Message type catalogue

Full details in `references/MESSAGE_TYPES.md`. Quick reference:

| Type | Priority | After sending | Use when |
|---|---|---|---|
| `status` | informational | keep working | heartbeat every ~5 min |
| `plan_approval` | blocking | STOP | before starting implementation (if gate enabled) |
| `question` | blocking | STOP | ambiguity blocks correct work |
| `stuck` | blocking | STOP | tried multiple approaches, can't proceed |
| `escalation` | blocking | STOP | need elevated permissions or scope change |
| `handover` | blocking | STOP | giving up, passing to human |
| `progress` | informational | keep working | milestone reached |
| `fyi` | informational | keep working | found something interesting |

## Reading responses

After you've been re-engaged following a blocking message, call
`check_messages` to read any responses. Don't assume the answer is
already in your context — the orchestrator passes it via the tool,
not inline.

```
# After re-engagement, first thing:
check_messages() → [{"in_reply_to": "msg-123", "body": "Go with option A", "author": "maia"}]
```

## The five anti-patterns

Full discussion in `references/ANTI_PATTERNS.md`. Short list:

1. **Spamming status messages** — every 5 minutes is the target, not every 5 seconds.
2. **Blocking when informational would do** — save `blocking` for when you genuinely cannot proceed.
3. **Sending plan approval when not required** — check the manifest first.
4. **Asking questions without options** — good questions have specific choices and a preferred answer.
5. **Forgetting to check messages after re-engagement** — the response is there, but only if you ask for it.

## See also

- `references/MESSAGE_TYPES.md` — full type catalogue with examples
- `references/EXAMPLES.md` — worked examples of every message type
- `references/ANTI_PATTERNS.md` — common mistakes
