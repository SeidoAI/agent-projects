# Workflow: Triage

> **Compliance reminder.** `tripwire validate` is your accountability
> surface. Run it after every change. Exit code 0 → proceed. Non-zero
> → STOP and address findings. **You MUST NOT skip validation.**

Processing inbound suggestions — comments on existing issues, messages
from coding agents, bug reports, or new requests — into actionable
project changes. This is the "someone said something, now what?" flow.

## Sources of inbound

- **Comments on issues** — humans or agents adding notes to
  `issues/<KEY>/comments/`
- **Agent messages** — blocking or informational messages from a
  coding agent (`question`, `stuck`, `escalation`, `fyi`)
- **Post-completion comments** — a completed session's
  `post-completion-comments.md` listing suggested follow-ups
- **Bug reports** — external bug reports landing in an inbox

## Procedure

### 1. Read the inbound item in full

Do not skim. If it's a comment thread, read every comment. If it's an
agent message, read the priority and body carefully.

### 2. Classify

| Classification | Action |
|---|---|
| Actionable now | Create a new issue (step 3). |
| Needs more info | Add a `question` comment to the relevant issue (step 4). |
| Duplicate | Comment on the existing issue linking the duplicate (step 5). |
| Won't do | Comment with rationale; mark any related session/epic as unaffected (step 5). |
| Epic / strategic | Defer to human planning; write a summary comment; do not create issues. |

### 3. For "actionable now" items

Follow `WORKFLOWS_INCREMENTAL_UPDATE.md` to create a new issue.

Capture:

- **Context** — what prompted this item
- **Requirements** — concrete acceptance criteria, not vague goals
- **Dependencies** — what needs to be in place first
- **Concept nodes** — does this touch an existing node? Create
  `[[references]]` in the body so the graph stays connected

Run `tripwire next-key --type issue` for the key. Reference any
existing nodes from the body. If this introduces a new concept (new
endpoint, new model, new decision), create the node file too.

### 4. For "needs more info" items

Use the `Write` tool to add a `question` comment to the relevant
issue (or respond to the agent message). Start from
`examples/comment-status-change.yaml` but change `type: status_change`
to `type: question`.

Your question must:

- Reference the inbound item by quote or comment id
- Be specific about what information you need
- Suggest options when possible

### 5. For duplicates / won't-dos

Use the `Write` tool to add a comment to the existing issue. Mark the
inbound item as processed (update its status in the source, if
applicable — via `tripwire transition` if the source is a tripwire
instance with a status field).

### 6. Validate and commit

Run:

```bash
tripwire validate
```

Exit 0 → commit. Non-zero → STOP and fix. Every new issue, every new
comment, every new node must pass the gate.

If any step fails: read the validator finding, fix the root cause,
re-run.

## Red flags — triage-specific rationalizations

| Agent thought | Reality |
|---|---|
| "This inbound is low-priority, I'll ignore it" | You don't ignore inbounds. Create a comment on the relevant issue acknowledging it, even if you defer the work. |
| "I'll create the issue now and figure out the scope later" | Triage means decide scope *now*. A scopeless issue is PM debt. |
| "I'll flip the issue's status to track this triage" | Use `tripwire transition issue-closure <KEY> <target>`. Do not edit `status:` by hand. |

## See also

- `WORKFLOWS_INCREMENTAL_UPDATE.md` for the mechanics of small edits.
- `SCHEMA_COMMENTS.md` for the comment file format.
- `CONCEPT_GRAPH.md` for when to create a node.
- `docs/WORKFLOW_ACTIONS.md` for every CLI command and transition.
