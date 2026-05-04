---
name: pm-session-complete
description: Close out a session — review, artifacts, node reconciliation, cleanup.
argument-hint: "<session-id> [closing note]"
---

You are the project manager. Load the project-manager skill if not active.

$ARGUMENTS

Workflow:

1. Parse `<session-id>` from arguments.
2. Run `tripwire session complete <session-id> --dry-run` to preview the
   close-out. If it fails, address the issue (e.g., missing artifacts,
   PR not merged) and retry.
3. If the session's PR hasn't been reviewed at its current HEAD:
   run `/pm-session-review <session-id>`. Handle blocking findings
   (exit code 2 refuses completion) before proceeding.
4. Review proposed insight-driven node additions/updates from
   `sessions/<session-id>/insights.yaml` (if present):
   - Run `tripwire session insights list <session-id>`.
   - For each proposal: accept
     `tripwire session insights apply <session-id> --proposal <id>` or reject
     `tripwire session insights reject <session-id> --proposal <id> --reason "..."`.
5. Record the workflow prompt-check:
   `tripwire prompt-check invoke pm-session-complete <session-id> --status completed`.
6. Run `tripwire session complete <session-id>` (real — drops `--dry-run`).
7. Run `tripwire validate` — the Layer 3 coherence check should
   pass now that issues and session both read `done`.
8. Commit: `complete: <session-id> (<comma-separated issue keys>)`.
9. Report back:
   - Issues closed
   - Nodes updated (with downstream impact via `tripwire refs reverse`)
   - Sessions unblocked
   - Recommended next launches
