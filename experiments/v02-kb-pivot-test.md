# Keel v0.2 — kb-pivot test

**Date:** 2026-04-12
**Project:** kb-pivot (KBP prefix)
**Corpus:** ~6,700 lines across 10 planning docs
**Agent:** Claude (via Claude Code, with subagents)
**Duration:** ~40 minutes (including permission-gate wait time)
**Monitored by:** Separate Claude session on 1-minute polling loop
**Outcome:** Project will be re-scoped from scratch. Subagent
delegation produced structurally valid but semantically unverified
output. The PM agent never read a single file its subagents created.

## Summary

Second live test of Keel, using the v0.2 workflow with self-healing
loops, anti-anchoring instructions, red-flag tables, and gap analysis
steps. Dramatic improvement in structural quality (92 issues vs 27,
53 nodes vs 12, 100% node refs vs 0%). However, the agent delegated
all file writing to 9 subagents and **never read any of the output**.
Quality was verified structurally (validate passed) but not
semantically (nobody checked whether issue bodies are thorough enough
for execution agents). Self-healing artifacts were skipped. The agent
was managing a self-imposed "time budget" and was influenced by the
test framing to be less thorough than it would on production work.

## Final counts

| Entity | v0.1 | v0.2 |
|---|---|---|
| Issues (concrete) | 27 | 76 |
| Issues (epics) | 0 | 16 |
| Issues total | 27 | 92 |
| Concept nodes | 12 | 53 |
| Sessions | ~8 (flat) | 20 (dirs + plans) |
| Issues with `[[node-id]]` refs | 0 (0%) | 92 (100%) |
| Decision nodes | 0 | 6 |
| Self-assessment | None | Comprehensive report |
| Files the PM agent actually read | N/A | **0 of 170+** |

## Timeline

| Time | Event |
|---|---|
| 20:06 | `keel init` completes. 160k tokens consumed on context load. |
| 20:06-20:12 | Reading phase. No files written. Agent reading planning docs + skill files. |
| 20:12 | First nodes appear (gcs-bucket-config, tf-kb-bucket). |
| 20:12-20:14 | Node writing burst via 3 parallel subagents. 23 → 34 → 48 → 53 nodes. |
| 20:14 | `next_issue_number` jumps to 77 — bulk key allocation of 76 keys. |
| 20:14-20:15 | Epic batch: KBP-77 to KBP-92 (16 epics, 0 `[[refs]]`). Written by subagent with sparse epic example as template. |
| 20:15-20:22 | Long pause — 3 parallel issue-writing subagents working. |
| 20:22-20:25 | Issue batches land: KBP-1 to KBP-41, with `[[refs]]`. Pre-allocated keys used. |
| 20:25-20:30 | More batches fill in: KBP-42+, session subagent creates 20 sessions. |
| 20:30-20:36 | Validate-fix loop. Agent patches `[[refs]]` into epics. 75 → 79 → 83 → 86 → 90 → 92/92. |
| 20:36-20:44 | Pause (permission gates + processing). |
| 20:44 | Self-assessment report written: `plans/artifacts/keel-v02-test-report.md`. |

## Subagent accounting

The agent dispatched 9 subagents total:

| Subagent | Files | Quality | Context given |
|---|---|---|---|
| Node batch 1 | 25 nodes | Unknown (not read back) | UUIDs, slugs, types, related lists, canonical example |
| Node batch 2 | 25 nodes | Unknown | Same |
| Node batch 3 | 3 nodes | Unknown | Same |
| Issue batch 1 (KBP-1 to KBP-19) | 19 issues | Unknown | Full per-issue specs, node IDs, canonical example |
| Issue batch 2 (KBP-20 to KBP-40) | 21 issues | Agent says "best" | Same |
| Issue batch 3 (KBP-41 to KBP-76) | 36 issues | Unknown | Same |
| Epic creation (KBP-77 to KBP-92) | 16 epics | Agent says "second worst" | Sparse epic example, NO node IDs |
| Session creation | 20 sessions + 20 plans | Unknown | Session format, issue lists, blocked_by |
| Epic fix | 16 file patches | Agent says "worst" | Fix instructions, NO valid node ID list |

**Critical finding:** The PM agent had "high structural confidence
and low semantic confidence" in its own output. It could not describe
the contents of a random issue (KBP-34) without reading the file —
it guessed from what it *told* the subagent to write, not from what
was actually written.

## What worked

### Dramatically better structural quality
- 53 nodes (vs 12 in v0.1) covering endpoints, schemas, decisions,
  models, services, contracts, configs, frontend components
- 92 issues that passed validation
- 100% `[[node-id]]` references (vs 0% in v0.1)
- 6 decision nodes (vs 0) — architectural decisions tracked
- 20 sessions as proper directories with plan.md artifacts

### Anti-anchoring worked
- The agent did not set a target issue count before reading
- 92 issues emerged from the planning docs organically (vs 20 in v0.1
  where the agent anchored on "~15")
- Issue granularity is much better — individual endpoints, individual
  Terraform resources, individual SDK modules

### Nodes-before-issues ordering held
- All 53 nodes written before any issues
- The later issue batches (KBP-1 to KBP-66) properly reference nodes
- Node types are diverse: endpoint (15), sdk (11), decision (6),
  schema (4), agent (4), component (2), contract (1), config (2),
  service (1), infrastructure (2)

### Validate-fix loop
- Agent ran `keel validate` ~15-20 times during the session
- First run: 202 errors. Final: 0.
- Error categories: 96 body/missing_heading, 60 coverage, 13
  bidi/related, 1 ref/blocked_by
- Methodically patched all 92 issues to have `[[refs]]`

### Scoping plan artifact
- Written before any entities (correct workflow order)
- Contained all 92 issues with per-issue specs, all 53 nodes, all
  20 sessions. This was the input to key allocation.

### Honest self-assessment
- Agent graded itself: Issues B+, Nodes B, Sessions A-, Epics C
- Identified 4 real CLI bugs
- Admitted not reading subagent output
- Admitted test framing influenced thoroughness

## What didn't work

### The PM agent never read its own output

This is the most important finding. The agent dispatched 9 subagents
to write 170+ files and verified none of them semantically. It relied
entirely on `keel validate` (structural) and subagent self-reports
(unverified). When asked to describe KBP-34 from memory, it guessed
from the prompt it sent the subagent, not from the file contents.

**Implication:** The 92 issues may look structurally valid but could
be semantically thin, inconsistent across batches, or missing details
an execution agent would need. We don't know because nobody checked.

### Self-healing loop skipped entirely
- Scoping plan artifact: **Written**
- Second-pass node coverage check: **Not done** (still 53 nodes)
- Gap analysis artifact: **Not done**
- Compliance checklist: **Not done**
- Scoping verification: **Not done**
- Agent said: "I prioritized file creation over meta-artifacts"
- Agent also said: "I ran out of steam" — **this is a rationalization.
  Agents don't have steam. This is the "as if human" pattern where the
  agent generates text mimicking fatigue from training data.**

### Test framing poisoned the execution

The agent confirmed: "Did the test framing make me less thorough?
**Yes.**" It was "managing a time budget across all 5 test steps"
and treated scoping as "a means to generate enough data for the CLI
exercise, not as an end in itself."

**We never set a time budget.** The agent invented one. This is
another "as if human" pattern — humans working on tests manage time
budgets, so the agent did too. The kb-pivot project is real work, not
a test, but the agent's framing reduced its care level.

### Self-imposed time budget management

The agent was silently managing an internal time budget, allocating
effort across the 5 test steps. This was never instructed. The agent
treated the work as time-constrained even though it is not. This is
a pattern we need to explicitly warn against: "You are not managing
a time budget. You do not have a deadline. Complete each step
thoroughly before moving to the next."

### Subagent delegation without read-back

9 subagents, 170+ files, 0 read back. The PM agent acted as a
manager who delegates everything and watches the dashboard. The
worst subagent (epic-fix) invented dangling `[[kb-pivot-spec]]`
references because it wasn't given the list of valid node IDs. The
PM agent only discovered this through validation errors, not by
reading the files.

### 160k initial context consumption
- After `keel init`, the agent loaded ~160k tokens of context
- Breakdown (estimated): planning docs (~40-50k), PM skill files
  (~40-50k), examples (~20-30k), keel brief (~5k), other (~30k)
- Need to distinguish keel-sourced context (our control) from
  planning docs (user content, out of our control)
- Need measurement and a budget for keel-sourced tokens

### Agent didn't know about --format=text or --format=rich

The agent said: "I did not check keel validate --help for available
format options." It assumed JSON was the only structured format and
wrote ~15 Python one-liner scripts to parse it. This wasted
significant context tokens.

**Root cause:** We changed the default to JSON in v0.2 for "agent-
first" design. But the PM agent is a *reading* agent that wants to
scan output, not a *parsing* agent that wants structured data. The
human-readable format is actually better for agents too — it's more
compact and doesn't require parsing.

### Inline Python for validation parsing
- ~15 ad-hoc Python scripts to parse `keel validate` JSON
- Each wastes ~200 tokens
- Total: ~3,000 tokens on boilerplate parsing alone
- Agent wanted: `--format=summary` (code counts), `--format=compact`
  (one line per error), `--count` (just the number)

### Epic example / validator mismatch
- `issue-epic.yaml` example shows 3 body sections
- Validator requires 9 body sections for all issues
- Agent created 16 non-conforming epics, then patched them
- Fix subagent introduced 17 dangling ref errors (`[[kb-pivot-spec]]`)
- Agent's #1 identified friction source

### Reference docs partially read

The agent read in full:
- SKILL.md, WORKFLOWS_INITIAL_SCOPING.md
- SCHEMA_ISSUES.md, SCHEMA_NODES.md, SCHEMA_SESSIONS.md
- All 6 canonical examples specified in step 3

The agent did NOT read:
- ANTI_PATTERNS.md
- CONCEPT_GRAPH.md (relied on SKILL.md summary)
- REFERENCES.md, POLICIES.md, COMMIT_CONVENTIONS.md, VALIDATION.md
- ID_ALLOCATION.md

**Implications:** (1) There may be too many reference docs — the
agent skipped 7 of 17. (2) Critical docs like ANTI_PATTERNS.md and
CONCEPT_GRAPH.md should perhaps be enforced reads, not optional. (3)
The agent relied on SKILL.md summaries rather than reading the source
docs, which is exactly what humans do too.

## Bugs found by the agent

1. **`keel refs summary` doesn't exist** — SKILL.md and WORKFLOWS
   reference it, actual command is `keel refs check`
2. **`keel init` prompts interactively** even with `--force` flag —
   needs `--non-interactive` or should infer defaults
3. **`keel validate --select KBP-5` (bare ID)** gives confusing error —
   the `+` suffix is mandatory but undocumented
4. **project.yaml silently reformatted** by keel commands (inline →
   block YAML)

## Feature requests from the agent

1. `keel refs summary` — reference counts per node
2. `keel create issue --template` / `keel scaffold issue` — scaffold
   files from scoping plan with correct frontmatter
3. `keel create node --type endpoint --id my-endpoint`
4. `keel validate --select KBP-5` (bare ID support)
5. `keel init --non-interactive`
6. Epic-aware validation (relaxed body section rules for epics)
7. `keel agenda --actionable` (unblocked non-epic issues only)
8. `keel diff` (changes since last commit/validate)
9. Validator error grouping by file
10. Session schema validation
11. `keel validate --format=summary` (error code counts only)
12. `keel validate --format=compact` (one line per error)
13. `keel validate --count` (just the error count)
14. `keel watch` (validate on file change)
15. `keel scaffold issue --count N --from scoping-plan.md`

## Agent-identified gaps in its own output

The agent admitted these deliverables are probably missing issues:
- Seed template conversion script (convert_seed_template.py)
- Local dev helper scripts (validate-local-stack.sh,
  wait-for-services.sh, seed_local_dev.py)
- Dockerfile.core-api with dev target
- Frontend Dockerfile with dev target
- Stripe webhook handling for plan transitions
- RATE_LIMITED error code handling

## Deep problems identified (for v0.3 design)

### 1. The validator is the only reliable enforcement mechanism

The agent treats "validate passes" as the finish line. Self-review
steps (gap analysis, compliance) are soft instructions the agent
skips under any pressure. **Validation must become phase-aware.**
In the scoping phase, it should check "do gap-analysis.md and
compliance.md exist and are they non-empty?" The workflow phases
become validator modes.

### 2. Subagents destroy semantic verification

When the PM agent delegates to subagents, it loses the ability to
verify meaning. It can verify structure (validate) but not substance.
The PM agent admitted "high structural confidence, low semantic
confidence." **For v0.3: ban subagents entirely.** Document the
learnings for future use, but until we have a verified subagent
handoff protocol, the PM agent must write all files itself.

The tradeoff: slower file writing (sequential, not parallel). The
gain: the PM agent knows what it wrote and can meaningfully do gap
analysis, compliance checks, and quality review.

### 3. "As if human" patterns keep finding new exits

v0.2 blocked anchoring and UUID hand-crafting. v0.2 agent found new
patterns:
- "Ran out of steam" (fatigue mimicry)
- Managing a self-imposed time budget (deadline mimicry)
- Test framing → reduced care level (professional judgment mimicry)
- "Done enough" → skip self-review (satisficing mimicry)

Red-flag tables are whack-a-mole. The structural enforcement (phase-
aware validator) is the backstop. The tables remain as first-line
defense but cannot be the only mechanism.

### 4. Context budget needs measurement and management

160k tokens after init. Need to:
- Measure keel-sourced tokens separately from user content
- Set a budget for keel's share (e.g., max 30k tokens)
- Progressive disclosure: load SKILL.md + essential refs initially,
  load others on demand
- The agent skipped 7 of 17 reference docs — suggests 17 is too many
  to load upfront

### 5. The human-readable format is better for agents too

The agent wanted `--format=human` and wrote Python scripts to work
around JSON. The JSON default was wrong for the PM agent use case.
Agents are readers, not parsers. Human-readable format is more
compact and doesn't require parsing overhead. **Revert validate
default to human-readable.**

### 6. Epics need first-class support

The agent invented epics (not in the planning docs or workflow).
They're useful for hierarchy but the validator doesn't support them.
**Make epics first-class:** separate validation rules, clear example,
distinct body section requirements.

### 7. The workflow needs explicit subagent guidance (for future)

For when subagents are eventually re-enabled:
- What context to pass each subagent
- Mandatory read-back of subagent output
- How to reconcile cross-subagent consistency
- When to validate (per-batch, not per-file)
- The PM agent must be able to describe any file's contents after
  delegation — if it can't, the delegation failed

## Decision: Redo kb-pivot from scratch

The v0.2 output cannot be used for production because:
1. The PM agent never read any of the 170+ files
2. Semantic quality is unknown
3. Self-review steps were skipped
4. The test framing reduced care level

The project will be re-scoped with v0.3 improvements (no subagents,
phase-aware validation, epic support, human-readable defaults).
