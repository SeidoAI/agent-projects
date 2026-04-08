# Messaging Anti-patterns

Common ways agents misuse the messaging system, and what to do
instead.

## 1. Status spam

**Bad**: sending a `status` message after every tool call.

```json
{"type": "status", "body": {"state": "implementing", "summary": "Wrote one line."}}
{"type": "status", "body": {"state": "implementing", "summary": "Wrote another line."}}
{"type": "status", "body": {"state": "implementing", "summary": "Still implementing."}}
```

The UI ends up with a thousand identical badges, nobody can read them,
and the signal-to-noise ratio collapses.

**Good**: target every 5 minutes of active work, plus every `state`
transition. Between updates, just work — don't narrate every step.

## 2. Blocking when informational would do

**Bad**: sending a blocking `question` for something you could figure
out yourself.

```json
{"type": "question", "priority": "blocking", "body": "Should I use snake_case or camelCase for field names?"}
```

Now your session is halted, a human has to respond, and you've
burned an iteration on something a 10-second glance at the existing
code would answer.

**Good**: check the existing codebase conventions first. If every
existing field is `snake_case`, use `snake_case` without asking. Save
blocking questions for genuine ambiguity where the answer isn't in
the project.

## 3. Sending plan approval when not required

**Bad**: sending `plan_approval` on every session regardless of
manifest.

```json
{"type": "plan_approval", "priority": "blocking", "body": "My plan is..."}
```

If the project's `templates/artifacts/manifest.yaml` has
`approval_gate: false` on the plan artifact, you've just halted your
session for no reason — the orchestrator has nothing to do, and a
human has to manually re-engage you.

**Good**: Read
`<project>/templates/artifacts/manifest.yaml` first. Look for the
`plan` entry's `approval_gate` field. Only send `plan_approval` if
it's `true`.

## 4. Asking questions without options

**Bad**:

```json
{"type": "question", "priority": "blocking", "body": "I'm not sure how to handle this. What should I do?"}
```

The human now has to ask you for context, think about options, AND
make a decision. Three round-trips instead of one.

**Good**: Give the human a choice menu with your preferred answer
and reasoning:

```json
{
  "type": "question",
  "priority": "blocking",
  "body": "## Ambiguity in SEI-42\n\nThe ticket says X but the contract says Y.\n\n**Options**:\n- A: do X (matches ticket)\n- B: do Y (matches contract)\n\n**My preference**: A — the ticket is more recent. Confirm?"
}
```

Now the human can respond with "A" or "B" in one line.

## 5. Forgetting to check messages after re-engagement

**Bad**: after being re-engaged, immediately starting to code.

```
[re-engaged after plan_approval]
→ writes code
→ human's response said "rejected, use different approach" but you never saw it
→ waste
```

**Good**: immediately after re-engagement, call `check_messages()`
and parse the response before doing anything else:

```
[re-engaged]
→ check_messages() → [{"in_reply_to": "msg-123", "body": "Approved, but also validate email format", "decision": "approved"}]
→ apply the addendum about email validation
→ then proceed with implementation
```

The response is never in your tool-call context automatically — you
must explicitly call `check_messages` to see it.

## 6. Conflating `status` and `progress`

**Bad**: using `progress` for the heartbeat.

```json
{"type": "progress", "body": "Still working on the auth endpoint, about halfway done."}
```

`progress` is for discrete milestones, not the periodic heartbeat. If
you use it for the heartbeat, you'll forget to also send `status`, and
the UI loses its live state badge.

**Good**: use `status` for the 5-minute heartbeat. Use `progress` for
milestones like "unit tests passing" or "implementation complete".

## 7. Handing over instead of asking

**Bad**: sending `handover` on the first sign of trouble.

```json
{"type": "handover", "body": "I don't know how to do this."}
```

Handover is for genuine impasse after you've tried multiple
approaches. Sending it on the first obstacle wastes the human's
time — you haven't given them anything to respond to except "start
over without me".

**Good**: try `question` first (with specific options), or `stuck`
(after 3+ attempts with details on each). `handover` is the last
resort.

## 8. Leaving out the `[[references]]`

**Bad**: describing things by name instead of referencing concept nodes.

```json
{"type": "question", "body": "About the user model — should I add a new field?"}
```

The PM agent triaging this has to figure out WHICH user model. If
there are five models in the project, this is ambiguous.

**Good**: reference the concept node.

```json
{"type": "question", "body": "About [[user-model]] — should I add a `last_login` field?"}
```

Unambiguous, greppable, and the PM agent can jump straight to the node.

## 9. Status messages with `blocking` priority

**Bad**:

```json
{"type": "status", "priority": "blocking", "body": {"state": "implementing", "summary": "Working on it."}}
```

Status is ALWAYS informational. If you set it to blocking, the
orchestrator halts your session, the human is confused about why,
and you waste an iteration on the re-engagement.

**Good**: `status` messages are always `priority: informational`, no
exceptions.
