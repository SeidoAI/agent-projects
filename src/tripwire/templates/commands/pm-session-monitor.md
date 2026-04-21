---
name: pm-session-monitor
description: Self-paced monitoring loop over executing sessions.
argument-hint: "[session-id ...] [auto-remediate <event-types>]"
---

You are the project manager. Load the project-manager skill if not active.

$ARGUMENTS

Auto-remediation defaults: read-only. You only elevate to auto-remediation
(re-engage stuck sessions, attach /autofix-pr, etc.) when the user's
arguments explicitly request it (e.g., "auto-remediate stuck" or
"auto-remediate ci-failure").

Workflow (self-paced via /loop dynamic mode):

1. Run `tripwire session monitor [session-ids] --format json`.
2. Parse the JSON snapshot.
3. Summarise in ≤10 lines: each session's status, turn, cost, latest tool,
   branch, PR status, any errors or stuck flags.
4. Take actions (read-only by default):
   - If any session's PR just opened and review hasn't run at this HEAD:
     run `/pm-session-review <session-id>`.
   - If any session is stuck: alert, don't re-engage unless user opted in.
   - If any session failed: alert, list resumption command.
   - If all sessions completed: run gap analysis and recommend next launches.
5. Decide pacing for next tick:
   - Active commits flowing: wait 60–90s.
   - Waiting for CI: wait 120–270s.
   - All idle (no commits 10+ min): wait 600–1200s.
   - Event detected: immediate.
6. ScheduleWakeup with the chosen interval.
7. At every tick, commit the monitor snapshot to the project repo:
   `chore: monitor snapshot <YYYY-MM-DDTHH:MM:SSZ>`.
