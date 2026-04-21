# Workflow: Incremental Update

The workflow for small surgical edits to an existing project — changing
one issue's status, adding a comment, creating a single new node,
responding to an orchestration event. This is the common case after the
initial scoping is done.

## Procedure

### 1. Front-load context (still cheap)
```bash
tripwire brief
```
Even for small updates, this is worth running — it confirms the current
project shape and catches stale assumptions.

### 2. Read the entity you're touching
```bash
cat issues/<KEY>/issue.yaml
# or: cat nodes/<id>.yaml
# or: cat sessions/<id>.yaml
```

### 3. Decide the edit type

- **Status change / small frontmatter tweak** → use `Edit` tool on the
  file, change the value, update `updated_at`. Don't rewrite the whole
  file unless you're changing the body too.
- **Comment** → write a new file at
  `issues/<KEY>/comments/<NNN>-<topic>-<date>.yaml`. Use the next
  sequence number (look at existing comments in that directory). See
  `examples/comment-status-change.yaml`.
- **New concept node** → write a new file at
  `nodes/<id>.yaml`. Use the example most similar to what you're
  creating (endpoint, model, decision, config, contract). Then add
  `[[<id>]]` references to wherever it's needed.
- **New issue** → call `tripwire next-key --type issue` for the
  key, then write `issues/<KEY>/issue.yaml`. See the initial scoping workflow
  for the full issue-creation procedure.
- **Session update (e.g. re-engagement event)** → edit
  `sessions/<id>.yaml` to append an engagement entry. Don't overwrite
  existing engagements — append only.

### 4. Update the concept graph if needed
If you touched code that a node points to, rehash the node:
- Read the node file
- Compute the new SHA-256 of the referenced file (or line range)
- Update `source.content_hash` and `updated_at`

If the validator already reports the node as stale, run with `--fix` (it
cannot rehash, but it can at least flag and report).

### 5. Validate
```bash
tripwire validate --strict
```
Fix every error. Re-run until clean.

### 6. Commit
Per `COMMIT_CONVENTIONS.md`. Smaller commits for smaller updates —
one commit per logical edit is fine.

## Common cases

### Status change (e.g. `todo` → `in_progress`)
1. Read the issue file
2. Edit the `status` field
3. Update `updated_at`
4. Add a `status_change` comment at `issues/<KEY>/comments/NNN-start-YYYY-MM-DD.yaml`
5. Validate

### Response to a status message from a coding agent
1. Read the current session file
2. Update `current_state` to match the message
3. Update `updated_at`
4. Validate

### New node created by a coding agent's PR
1. Read the PR's diff to find the new node file
2. Check that the node's `source.content_hash` matches the actual content
3. Check that all `[[references]]` to this node resolve
4. Validate

## Red flags — update-specific rationalizations

| Agent thought | Reality |
|---|---|
| "It's just one field change, I don't need to validate" | You do. One field change can break a reference chain. Always validate. |
| "I'll update the status without checking `refs reverse`" | Run `tripwire refs reverse <id>` first. Status changes on a heavily-referenced entity may need downstream updates. |

## See also

- `WORKFLOWS_INITIAL_SCOPING.md` for bulk creation.
- `SCHEMA_COMMENTS.md` for the comment file format.
- `CONCEPT_GRAPH.md` for node creation rules.
