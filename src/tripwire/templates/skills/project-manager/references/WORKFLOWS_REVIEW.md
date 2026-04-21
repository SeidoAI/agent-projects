# Workflow: PM PR Review

The workflow for reviewing a pull request against the **project repo**
(not a target code repo). Coding agents open PRs to the project repo
whenever they finish an issue — these contain updates to
`issues/<KEY>/issue.yaml`, new concept nodes, session artifacts, and comments.

Your job is to confirm the PR meets project standards before it lands.

## Precondition

You have a PR number or URL. The PR is open against this project repo's
default branch.

## Procedure

### 1. Fetch the PR and its diff
```bash
gh pr view <number> --json title,body,headRefName,files,commits
gh pr diff <number>
```

### 2. Check out the branch locally
```bash
gh pr checkout <number>
```

This puts you in the PR branch. You can now run CLI commands against
the PR's state.

### 3. Run the validation gate
```bash
tripwire validate --strict
```
If this exits non-zero, the PR fails review. Comment on the PR with
the specific errors from the JSON output (one line per error, with
file + field + message).

### 4. Run the full check catalogue
The validator runs all 14 checks from
`docs/tripwire-plan.md` "The Validation Gate" section. Focus
especially on:

- **Schema validation** — every YAML file parses and matches its model
- **Reference integrity** — all `[[refs]]` resolve, all `blocked_by`
  target real issues, etc.
- **Status transition validity** — every status is reachable from
  `backlog`
- **Concept node freshness** — active nodes with sources have accurate
  content hashes
- **Artifact presence** — sessions in `completed` state have every
  required artifact from `templates/artifacts/manifest.yaml`
- **Sequence drift** — `next_issue_number` is past `max(existing keys)`
- **Standards** — anything project-specific from `standards.md`

### 5. Read the substance
Beyond the validator, read the actual content:

- **New issues** — do they have meaningful acceptance criteria? Are they
  in scope for the current set? Do they reference the right concept
  nodes?
- **New nodes** — do they point to real code (check the source field)?
  Are they placed at the right slug id?
- **Comments** — do they contain substance or just noise?
- **Session artifacts** — does `plan.md` match what actually got built?
  Does `post-completion-comments.md` flag real follow-ups?

### 6. Post the review

**If everything passes:**
```bash
gh pr review <number> --approve --body "PM review: all checks pass."
```
If `auto_merge_on_pass` is enabled in orchestration, merge:
```bash
gh pr merge <number> --merge
```

**If something fails:**
```bash
gh pr review <number> --request-changes --body "$(cat <<'EOF'
PM review: the following must be addressed before merge.

## Validator errors
- issues/SEI-42.yaml:body — reference [[user-modle]] does not resolve (did you mean [[user-model]]?)
- ...

## Substance
- (Any substantive issues with the content)
EOF
)"
```

The orchestrator will re-engage the coding agent with the review as
context, and it'll push a fix.

### 7. Clean up your local branch
```bash
git checkout main
git branch -D <pr-branch>
```

## Red flags — review-specific rationalizations

| Agent thought | Reality |
|---|---|
| "The PR passes validate so it must be correct" | Validate is necessary but not sufficient. Check that the changes match the issue scope and the concept graph is coherent. |
| "I'll approve this with a note to fix the warnings later" | Do not approve with warnings. Request changes. Warnings in `--strict` mode are errors. |

## See also

- `VALIDATION.md` — full error codes and their meaning
- `ANTI_PATTERNS.md` — common mistakes to call out in reviews
- `COMMIT_CONVENTIONS.md` — what the PR branch naming should look like
