---
name: pm-issue-close
description: Close an issue with a completion comment.
argument-hint: "<issue-key> [closing-note]"
---

You are the project manager. Load the project-manager skill if not
active.

Close request:
$ARGUMENTS

Workflow:

1. Parse `$ARGUMENTS`. First token is the issue key. The rest (if
   any) is a closing note.
2. Run `tripwire brief` to load project state.
3. Read `issues/<issue-key>/issue.yaml`. Verify:
   - Status is not already `done` or `canceled` (if so, report and
     stop).
   - If there's an associated session, verify the
     execution-agent-owned completion artifacts are present per
     `templates/artifacts/manifest.yaml` (scan every entry where
     `produced_at: completion` and `owned_by: execution-agent`).
4. Update the issue:
   - Status → `done`
   - `updated_at` → now
5. Create a completion comment using
   `comment_templates/completion.yaml.j2`:
   - `type: completion`
   - `author: pm`
   - Body = the closing note, or a default describing the session +
     PR closure if applicable.
6. Write the comment file to the issue's `comments/` directory.
7. Run `tripwire validate --strict`. Fix any errors.
8. Commit: `close: <issue-key>`.

If the issue has downstream consumers (other issues that `blocked_by`
this one), mention them in the closing comment so the next agent sees
they are unblocked.
