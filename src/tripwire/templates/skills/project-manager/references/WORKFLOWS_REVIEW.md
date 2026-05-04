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

### 2.5. Write per-issue `verified.md` artifacts
```bash
tripwire session review <session-id> --write-verified
```

This generates a `verified.md` file under `docs/issues/<KEY>/` for
every issue closed by the session, summarising the on-disk evidence
(diff, tests, AC walk) the PM observed during review. It must run
**before** approve/merge — once the branch is gone, the per-issue
evidence cannot be reconstructed without re-checking-out the PR. The
post-merge reconciliation in step 8 reads these `verified.md` files
to understand which nodes the shipped behaviour diverged from;
skipping this step leaves step 8 with nothing to read and node
freshness drifts silently.

### 3. Run the validation gate
```bash
tripwire validate
```
If this exits non-zero, the PR fails review. Comment on the PR with
the specific errors from the JSON output (one line per error, with
file + field + message).

### 4. Run the full check catalogue
The validator runs all 14 checks from the "The Validation Gate"
section of `tripwire-plan.md` in the tripwire-workspace repo
(https://github.com/SeidoAI/tripwire-workspace/blob/main/docs/tripwire-plan.md).
Focus especially on:

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

### 8. Post-merge node reconciliation

After a PR merges with implementation that diverged from the body of
one or more concept nodes, the PM updates the node bodies to match
delivered behaviour. This is a recurring task — execution agents
prefer divergence-and-document over re-implement-to-match-spec, and
that's usually the right call. The PM closes the loop.

The trigger is the agent's PR comment from their self-review (Lens 3
typically): *"`[[file-watcher]]` references path X but I shipped Y."*
or *"`[[websocket-hub]]` describes a 2-missed-pings SLA but I
implemented prune-on-send-failure."*

For each surfaced divergence:

1. `tripwire refs reverse <node-id>` — see who else references the
   node so you know what may need cascading updates.
2. Read the node file. Read the relevant section of the agent's
   delivered code (the PR's diff line ranges).
3. **Default: update the node body to match shipped behaviour.** It's
   the cheaper and almost-always-correct call. Re-implementing the
   code to match the original node body makes sense only if the
   shipped behaviour is actually wrong (rare).
4. If shipped behaviour is wrong, file a follow-up issue describing
   the desired behaviour and link it from the node body's "see also";
   leave the node body unchanged for now.
5. **`source.content_hash`** only needs bumping if the underlying
   `source` file (the one the node points at) actually changed.
   Body-only edits do not require a content_hash bump.
6. Validate (`tripwire validate`) and commit. Convention:
   `reconcile: <node-list> after <pr-id>` — e.g.
   `reconcile: [[file-watcher]], [[websocket-hub]] after #10`.

Example commit messages from past reconciles:
- `reconcile: update concept nodes to match delivered implementation`
- `reconcile: [[node-service]] body after #9`

## Review feedback cycle

The procedure above describes one review pass. In practice a session
may need several iterations before merging — and that loop has its
own canonical shape (v0.7.5 §2.C3):

1. Agent ships PR. Process exits cleanly per the exit protocol. The
   draft PR (open since spawn-start, v0.7.5 item A) flips to ready at
   `session complete`.
2. PM reviews:
   a. Read the agent's self-review (the four-lens block from the
      spawn template).
   b. Walk the verification-checklist independently.
   c. Run `tripwire validate` against the project repo.
   d. Optionally dispatch sub-agents for independent bug scans
      and cross-cutting pattern analysis.
3. PM writes the structured PR-review artifact (v0.7.5 item D, ships
   in the follow-up PR).
4. PM posts findings on the PR — one comment per concern, each with
   a suggested fix. Mark severity (critical / real bug / nice-to-
   fix). The artifact is the PM's view; the PR comments are the
   agent's actionable list.
5. PM either approves+merges (no findings) **OR**
   `tripwire session reopen <id> --reason "..."` then
   `tripwire session spawn <id> --resume`.
6. Agent (resumed) reads PR comments + plan.md `## PM follow-up`
   section. Addresses each finding. Pushes. Posts a follow-up comment
   summarising what they changed per finding.
7. Loop steps 2–6 until verdict is approve+merge.
8. `tripwire session complete <id>`. Status → completed. The post-
   merge node reconciliation in **Procedure step 8** above runs once
   the cycle is closed — not per iteration.

`session reopen` is the explicit lifecycle slot for this loop
(rather than loosening the `completed` → `executing` guard in the
state machine). Each reopen records to
`~/.tripwire/logs/<project-slug>/audit.jsonl` so round-trip history
is queryable.

## Red flags — review-specific rationalizations

| Agent thought | Reality |
|---|---|
| "The PR passes validate so it must be correct" | Validate is necessary but not sufficient. Check that the changes match the issue scope and the concept graph is coherent. |
| "I'll approve this with a note to fix the warnings later" | Do not approve with warnings. Request changes. Warnings (heuristics) surface in validate output by default and must be resolved before approval. (Stage 2 will introduce `--heuristics-as-tripwires` to fail the run on heuristic hits — currently a no-op slot.) |
| "I'll skip `--write-verified` and reconcile straight from the diff post-merge" | Step 8 has no per-issue evidence to reconcile against once the branch is gone; node freshness drifts silently. Run step 2.5 every review. |

## See also

- `VALIDATION.md` — full error codes and their meaning
- `ANTI_PATTERNS.md` — common mistakes to call out in reviews
- `COMMIT_CONVENTIONS.md` — what the PR branch naming should look like
