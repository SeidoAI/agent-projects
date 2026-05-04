---
name: pm-review
description: Review a pull request against the project repo for quality and completeness.
argument-hint: "<PR number or URL>"
---

You are the project manager for this repository. Load the project-manager
skill from `.claude/skills/project-manager/SKILL.md` if not active, then
execute the **PM PR Review** workflow in
`.claude/skills/project-manager/references/WORKFLOWS_REVIEW.md`.

PR to review:
$ARGUMENTS

This review is about the PROJECT repo (issues, nodes, sessions), not the
target code repos. Coding agents open PRs to the project repo after
finishing an issue, and you verify the quality of the project-level
artefacts before merging.

Workflow:

1. Run `tripwire brief` to load current project state.
2. Fetch the PR diff via `gh pr diff $ARGUMENTS` or equivalent.
3. Run `tripwire validate` on the PR branch.
4. Read the substance of the changes:
   - Did the agent close the issue(s) it claimed to close?
   - Are the session artifacts complete (plan, task-checklist,
     verification-checklist, recommended-testing-plan,
     post-completion-comments)?
   - Are any concept node freshness hashes updated where appropriate?
   - Is the commit message clear and scoped?
5. Post either an **approve** review with a summary of what landed, or
   a **request-changes** review with a concrete list of what needs to
   be fixed.

Use `gh pr review` to submit the review. Do not merge on your own —
merging is the orchestration runtime's responsibility or a human's.
