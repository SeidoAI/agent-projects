# Policies (project-specific)

This file is a placeholder for project-specific rules and policies
that override or extend the packaged defaults. Every project can fill
it in with its own content.

## What goes here

Things that are true for **this project** but not for tripwire in
general:

- Required labels (e.g. "every issue must have a `domain/*` label")
- Agent-specific constraints (e.g. "backend-coder may only work in
  `src/api/`")
- Approval gates (e.g. "every issue touching `auth/` requires human
  plan approval")
- Coding style preferences beyond what `standards.md` already covers
- Review SLA (e.g. "PM agent reviews within 1 hour during business
  hours")
- Release cadence (e.g. "no merges on Fridays after 14:00")
- Data handling (e.g. "never commit fixture data with real emails")

## What does NOT go here

- General tripwire conventions (those live in `SCHEMA_*.md`,
  `WORKFLOWS_*.md`, and `ANTI_PATTERNS.md`).
- The project's `standards.md` (that's the top-level standards file the
  PM review checks against).
- Orchestration pattern configuration (that's in `orchestration/`).

## Default content

(Projects replace this section with their own policies.)

This project has no additional policies beyond the packaged defaults.
Edit this file to add them.

## See also

- `<project>/standards.md` — top-level project standards
- `WORKFLOWS_CODE_REVIEW.md` — PM review procedure
- `WORKFLOWS_NODE_RECONCILIATION.md` — post-merge node reconciliation
- `ANTI_PATTERNS.md` — common mistakes to avoid
