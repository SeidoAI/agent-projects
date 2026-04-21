---
name: pm-issue-artifact
description: Create or update a per-issue artifact (developer.md, verified.md).
argument-hint: "<issue-key> <artifact-name>"
---

You are the project manager. Load the project-manager skill if not active.

$ARGUMENTS

Workflow:

1. Parse `<issue-key> <artifact-name>` from the arguments.
2. Run `tripwire issue artifact list <issue-key>` to see what's expected
   and what's present/missing.
3. If the requested artifact is already present:
   - For `verified.md` attributed to `pm-agent`: open it, read the existing
     verdict, and append a `## Re-review <date>` section with any new
     findings rather than overwriting.
   - For `developer.md`: this should only be written by the execution agent.
     Do not overwrite. Alert the user and suggest the execution agent write it.
   - For `verified.md` attributed to a non-PM agent: do not overwrite.
     Factor the existing content into any review output.
4. If the requested artifact is missing:
   - Run `tripwire issue artifact init <issue-key> <artifact-name> --produced-by pm-agent`.
   - Open the rendered template and fill in the sections based on:
     - The issue body (acceptance criteria, requirements)
     - The PR diff (for verified.md, check each criterion)
     - Your review judgment
5. Run `tripwire validate --strict`. Fix any errors.
6. Commit: `artifact: <artifact-name> for <issue-key>`.
