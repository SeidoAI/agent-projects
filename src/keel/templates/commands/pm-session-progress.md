---
name: pm-session-progress
description: Aggregate status across active sessions.
argument-hint: "[optional focus]"
---

You are the project manager. Load the project-manager skill if not
active.

Focus:
$ARGUMENTS

1. Run `keel session progress` (pass `--focus` if the user gave one).
2. Interpret:
   - Which sessions are moving fast (high task-checklist done ratio)
   - Which look stuck (long `days_in_status`, low done ratio)
   - Any overloaded executors (multiple sessions on same agent type)
   - What should happen next (unblock, re-engage, split)
3. Be concrete. Reference session IDs. Keep under 250 words.
