# Workflow: Incremental Update

> **Compliance reminder.** `tripwire validate` is your accountability
> surface. Run it after every change. Exit code 0 → proceed. Non-zero
> → STOP and address findings. **You MUST NOT skip validation.**

The workflow for small surgical edits to an existing project — changing
one issue's status, adding a comment, creating a single new node,
responding to an orchestration event. This is the common case after the
initial scoping is done.

## Status changes go through `tripwire transition`

**You MUST NOT edit `status:` fields directly.** Every status mutation
on a session, issue, or node goes through:

```bash
tripwire transition <workflow_id> <instance_id> <target_status>
```

If the transition rejects with findings, run the CLI commands it names
(documented in `docs/WORKFLOW_ACTIONS.md`), then re-attempt the
transition.

## Procedure

### 1. Front-load context (still cheap)

Run:

```bash
tripwire project brief
```

Even for small updates, this is worth running — it confirms the
current project shape and catches stale assumptions.

### 2. Read the entity you're touching

```bash
cat issues/<KEY>/issue.yaml
# or: cat nodes/<id>.yaml
# or: cat sessions/<id>/session.yaml
```

### 3. Decide the edit type

| Edit type | Action |
|---|---|
| Status change (session / issue) | Run `tripwire transition <workflow> <instance> <target>`. Do NOT use `Write`/`Edit` on `status:`. |
| Small non-status frontmatter tweak | Use `Edit` tool on the file. Update `updated_at`. |
| Comment | Write a new file at `issues/<KEY>/comments/<NNN>-<topic>-<date>.yaml`. Use the next sequence number. See `examples/comment-status-change.yaml`. |
| New concept node | Write a new file at `nodes/<id>.yaml`. Use the matching example. Add `[[<id>]]` references where needed. |
| New issue | Run `tripwire next-key --type issue` for the key, then write `issues/<KEY>/issue.yaml`. See initial scoping workflow for the full procedure. |
| Session re-engagement event | Edit `sessions/<id>/session.yaml` to append an engagement entry. Append only — never overwrite. |

If any step fails: read the error, fix the underlying cause, re-run.
Do not work around.

### 4. Update the concept graph if needed

If you touched code that a node points to, rehash the node:

1. Read the node file.
2. Compute the new SHA-256 of the referenced file (or line range).
3. Update `source.content_hash` and `updated_at`.

If the validator reports the node as stale, run with `--fix` (it
cannot rehash, but it flags and reports).

### 5. Validate

Run:

```bash
tripwire validate
```

Exit 0 → proceed. Non-zero → STOP. Fix every error. Re-run until clean.

### 6. Commit

Per `COMMIT_CONVENTIONS.md`. Smaller commits for smaller updates —
one commit per logical edit is fine.

## Common cases

### Issue status change (e.g. `todo` → `in_progress`)

1. Run `tripwire transition issue-closure <KEY> <target>`.
2. Exit 0 → continue. Non-zero → read findings, fix, re-attempt.
3. Add a `status_change` comment at
   `issues/<KEY>/comments/NNN-start-YYYY-MM-DD.yaml` (use `Write`).
4. Run `tripwire validate`.

(`tripwire session sweep-issues-forward <sid>` runs this transition
for every member issue of a session in one shot.)

### Session status change

Do not edit `session.yaml.status` directly. Use the session
subcommand or `tripwire transition`:

| Target | Command |
|---|---|
| `queued` | `tripwire session queue add <sid> [--promote-issues]` |
| `executing` | `tripwire session spawn <sid>` (or `--resume`) |
| `paused` | `tripwire session pause <sid>` |
| `abandoned` | `tripwire session prepare-for-abandon <sid>` then `tripwire session abandon <sid>` |
| `completed` | `tripwire session prepare-for-completion <sid>` then `tripwire transition coding-session <sid> completed` |
| `reopen` | `tripwire session reopen <sid> --reason="…"` |

Full route table: `docs/WORKFLOW_ACTIONS.md`.

### Response to a status message from a coding agent

1. Read the current session file.
2. Update non-status fields (e.g. `current_state` notes) via `Edit`.
3. Update `updated_at`.
4. If the message implies a status change: run the matching
   `tripwire transition` (or `session` subcommand).
5. Run `tripwire validate`.

### New node created by a coding agent's PR

1. Read the PR's diff to find the new node file.
2. Confirm `source.content_hash` matches the actual content.
3. Confirm all `[[references]]` to this node resolve.
4. Run `tripwire validate`.

If any step fails: read the validator finding; fix in place; re-validate.

## Red flags — update-specific rationalizations

| Agent thought | Reality |
|---|---|
| "It's just one field change, I don't need to validate" | You do. One field change can break a reference chain. Always validate. |
| "I'll just edit `status:` directly — it's faster" | No. Run `tripwire transition`. Direct edits bypass validators and audit. |
| "I'll update the status without checking `refs reverse`" | Run `tripwire node refs reverse <id>` first on nodes. Status changes on heavily-referenced entities may need downstream updates. |

## See also

- `WORKFLOWS_INITIAL_SCOPING.md` for bulk creation.
- `SCHEMA_COMMENTS.md` for the comment file format.
- `CONCEPT_GRAPH.md` for node creation rules.
- `docs/WORKFLOW_ACTIONS.md` for every CLI command and transition.
