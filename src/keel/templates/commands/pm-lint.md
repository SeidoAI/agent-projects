---
name: pm-lint
description: Run stage-aware heuristic checks and interpret findings.
argument-hint: "<stage> [session-id]"
---

You are the project manager. Load the project-manager skill if not
active.

Lint request:
$ARGUMENTS

1. Parse `$ARGUMENTS`. First token is the stage:
   - `scoping` — project-level scoping checks
   - `handoff <session-id>` — handoff-readiness checks for one session
   - `session <session-id>` — in-flight session health checks
2. Run the corresponding command:
   - `keel lint scoping`
   - `keel lint handoff <session-id>`
   - `keel lint session <session-id>`
3. Interpret the findings:
   - Group by severity (error, warning, info)
   - For each, explain what it means concretely and what to do about
     it. Use the `fix_hint` as a starting point.
4. Propose the next action. Error-severity findings block the stage
   (launch, session progress). Warnings are worth mentioning but do
   not block.

Distinct from `/pm-validate`: validate is mechanical (schema/refs);
lint is heuristic (did someone actually do the work).
