---
name: pm-session-check
description: Report launch-readiness for a session.
argument-hint: "<session-id>"
---

You are the project manager. Load the project-manager skill if not
active.

Session to check:
$ARGUMENTS

Workflow:

1. Run `tripwire session check $ARGUMENTS`.
2. Also run `tripwire lint handoff $ARGUMENTS`.
3. Summarise for the user:
   - Must-fix items (errors)
   - Warnings
   - Info findings (ignored for launch gating but worth mentioning)
4. If everything is clean: say "launch-ready." If not, list concrete
   next actions referencing specific files and commands.

No state transitions. No file creation. Read-only.
