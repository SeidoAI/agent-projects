# Message Types — Full Catalogue

Each message type has specific semantics, a priority default, and
specific post-send behaviour. The orchestration runtime branches on
`type` — picking the wrong type means the wrong automation fires.

## `status`

**Priority**: informational
**After sending**: keep working
**Schema**: structured body `{state, summary}`

Periodic heartbeat. The UI session card renders the most recent status
as a badge + summary line. The orchestrator writes `current_state`
back to `session.yaml` whenever a new status arrives, so humans
scanning the dashboard can see "what is every agent doing right now"
without opening individual sessions.

Rules:
- Send every 5 minutes of active work AT MINIMUM
- Send on every `state` transition (e.g. `investigating` →
  `planning`, `implementing` → `testing`)
- Use a `state` from `<project>/enums/agent_state.yaml`
- Keep `summary` to 1-2 plain sentences — this is a ticker, not an essay

## `plan_approval`

**Priority**: blocking
**After sending**: STOP and exit

Request human approval for the implementation plan before starting
code changes. Only required if the project has
`templates/artifacts/manifest.yaml` with `approval_gate: true` on the
plan artifact.

The body should be the full content of `plan.md` (or a link to it
once it's committed). The human responds with `approved` or
`rejected`, and the orchestrator re-engages you with a `plan_approved`
or `plan_rejected` trigger.

**Do NOT send this if `approval_gate: false`** — it pauses the
session unnecessarily. Check the manifest before every scoping job.

## `question`

**Priority**: blocking
**After sending**: STOP and exit

A specific, answerable question that blocks correct work. Good
questions:

1. Identify the source of ambiguity (quoting or referencing the
   conflicting text)
2. Present specific options (not just "what should I do?")
3. Include your preferred answer with reasoning

Bad questions waste both the human's and your own time:

- ✗ "What should I do?" (no options)
- ✗ "Is this right?" (no context)
- ✗ "Should I use X or Y?" (no reasoning about trade-offs)

If you find yourself about to ask a question, first check whether
the answer is already in the project:

- Read the relevant concept node (e.g. the `decision` type)
- Check `standards.md`
- Check the issue body for explicit execution constraints

## `stuck`

**Priority**: blocking
**After sending**: STOP and exit

You've tried 3+ approaches to the same problem and none have worked.
The body should describe:

1. What you're trying to do
2. What you've tried (each approach, why it failed)
3. Where you're stuck now

This is the "I need help" message. Use it sparingly — if you've only
tried one thing, that's not stuck, that's just starting.

## `escalation`

**Priority**: blocking
**After sending**: STOP and exit

You need something outside your current permissions or scope to
proceed. Examples:

- Need to touch a file in a repo you don't have write access to
- Need to make a product decision the ticket doesn't cover
- Need the scope of the issue expanded or reduced
- Discovered a blocking issue not yet in the project

The body should name the specific escalation needed and why.

## `handover`

**Priority**: blocking
**After sending**: STOP and exit

You're giving up on the work and passing it to a human. Use when:

- The task is genuinely beyond your capability
- You've hit a block that isn't "stuck" but clearly human judgement
- You've been re-engaged many times and suspect a loop

The body should be a full handover note: what's been done, what's
not, where the code is, what the next steps would be for a human
taking over.

Use this sparingly. Most "I should hand over" impulses are actually
"I should send a `question` with good options" — try that first.

## `progress`

**Priority**: informational
**After sending**: keep working

A milestone worth surfacing without blocking. Use for:

- "Tests written, starting implementation"
- "Implementation done, running test suite"
- "All tests passing, writing docs"

`progress` is optional — the orchestration runtime doesn't branch on
it. It's just for visibility.

Don't use `progress` where `status` fits better. `progress` is for
discrete milestones; `status` is for the periodic heartbeat.

## `fyi`

**Priority**: informational
**After sending**: keep working

Something interesting you found that's outside your scope. Use for:

- Unrelated bugs you noticed
- Refactoring opportunities
- Documentation gaps
- Things you'd do if you were working on this area but aren't

The PM agent reads `fyi` messages during triage to decide whether to
file follow-up issues.

## See also

- `EXAMPLES.md` — worked examples of every type
- `ANTI_PATTERNS.md` — how to use each type wrongly
