# Keel v0.3 — kb-pivot test

**Date:** 2026-04-12
**Project:** kb-pivot (KBP prefix)
**Corpus:** ~6,700 lines across 10 planning docs
**Agent:** Claude (via Claude Code, NO subagents)
**Duration:** ~45 minutes (including permission-gate wait time)
**Monitored by:** Separate Claude session on 1-minute polling loop
**Outcome:** Full 12-step workflow completed. All meta-artifacts
produced. Phase advanced to `scoped`. Pending commit.

## Summary

Third live test of Keel. v0.3 added phase-aware validation, subagent
ban, first-class epic support, human-readable format defaults, and
"DO NOT SKIP" checkpoint warnings. The PM agent executed the complete
scoping workflow — including gap analysis, compliance checklist, and
scoping verification — for the first time. It wrote every file itself
(no subagents), found 3 gaps during self-review, and produced 5
meta-artifacts. The phase-aware validator enforced the transition gate.

## Final counts

| Entity | v0.1 | v0.2 | v0.3 |
|---|---|---|---|
| Issues (concrete) | 27 | 76 | 60 |
| Issues (epics) | 0 | 16 | 16 |
| Issues total | 27 | 92 | 76 |
| Concept nodes | 12 | 53 | 34 |
| Sessions | ~8 (flat) | 20 (dirs) | 16 (dirs) |
| Issues with `[[node-id]]` refs | 0% | 100% (post-fix) | TBD (spot checks: 6+ per issue) |
| Decision nodes | 0 | 6 | 5 |
| Meta-artifacts produced | 0 | 0 (wrote test report instead) | 5 |
| Files agent personally wrote | N/A | 0 of 170+ | All 142+ |
| Gaps found in self-review | N/A | Skipped | 3 |
| Phase advanced to scoped | N/A | No (skipped) | Yes |

## Timeline

| Time | Event |
|---|---|
| 22:48 | `keel init --force` completes. v0.3 templates deployed. |
| 22:48-22:55 | Reading phase (~7 min). Agent reads keel brief, all 10 planning docs, canonical examples. No files written. |
| 22:55 | Scoping plan written (264 lines). `next_issue_number` → 74 (73 keys allocated). |
| 22:56-22:58 | Node writing phase. 34 nodes written sequentially. Decision nodes first, then infra, schemas, Firestore, SDK, endpoints, contracts. |
| 22:58 | First validation checkpoint (graph cache created). |
| 22:58-23:01 | Epic writing phase. KBP-1 through KBP-16 (16 epics) with correct `type/epic` label and 3-section body. |
| 23:01-23:18 | Concrete issue writing. KBP-17 through KBP-73 (57 issues). Validation checkpoint mid-batch at ~KBP-41. Agent fixed 3 stop-and-ask gaps and 4 bidi refs. |
| 23:18-23:23 | Session writing. 16 sessions created with session.yaml + plan.md. 2 initially missing plans, fixed. |
| 23:23-23:30 | 3 new issues created (KBP-74, 75, 76) — gaps found during review. |
| 23:30-23:35 | Gap analysis written (147 lines). Scoping verification written (76 lines). Task checklist written (41 lines). |
| 23:35-23:38 | Compliance checklist filled in (23 lines). All 5 artifacts marked `<!-- status: complete -->`. |
| 23:38 | Phase set to `scoped`. `keel validate --strict` passed. |
| ~23:40 | Agent running final status/agenda/refs commands. Commit pending. |

## What worked

### The full workflow executed

For the first time across 3 tests, the PM agent completed all 12
steps including the self-review loop (steps 8-10). v0.1 and v0.2
both skipped these steps. The phase-aware validator was the
enforcement mechanism — the agent couldn't advance to `scoped`
without the artifacts.

### No subagents — agent wrote and knows every file

142+ files written sequentially by the agent itself. When the agent
did the gap analysis, it was reviewing files it had personally
written, not files produced by subagents it never read. This makes
the self-review meaningful rather than performative.

### Scoping plan before entities

264-line scoping plan written as step 4, before any entities. The
plan included per-issue concept node refs, meaning the agent planned
the node-issue cross-references before writing either. In v0.2, nodes
and issues were written by different subagents that didn't share this
mapping.

### Gap analysis found real gaps

The agent found 3 missing deliverables during gap analysis:
- Uploads backend/frontend
- KB settings UI
- (third TBD — need to check KBP-74)

These became KBP-74, 75, 76. The self-healing loop produced
actionable results, not just a checkbox exercise.

### Epic support worked cleanly

16 epics with `type/epic` label, 3-section bodies (Context, Child
issues, Acceptance criteria). No validation errors from epics — the
v0.2 mismatch (96 `body/missing_heading` errors) is completely
eliminated.

### Correct entity ordering

Nodes (34) → epics (16) → concrete issues (57+3) → sessions (16).
This matches the workflow exactly and ensures `[[node-id]]` refs
resolve from the first issue written.

### Decision nodes first

The agent started with 5 decision nodes (`dec-neo4j-to-gcs`,
`dec-two-layer-storage`, etc.) before any other entity type. This
captures the "why" before the "what" — a quality improvement over
v0.2 which started with config/infra nodes.

### Validate-fix loop during writing

The agent ran validation checkpoints during issue writing and fixed
errors before continuing (3 stop-and-ask gaps, 4 bidi refs, 2
missing session plans). Not as frequent as "every 3-5 files" but
errors were caught and fixed mid-batch.

## What didn't work / deviations

### Fewer entities than v0.2

76 issues vs 92, 34 nodes vs 53, 16 sessions vs 20. This could be:
- Better: tighter scope, less redundancy, coarser but sufficient
  node granularity
- Worse: missing coverage that v0.2 caught

Needs Q&A to understand. The gap analysis found 3 gaps and resolved
them, so the agent did self-check. But whether 34 nodes is sufficient
coverage vs 53 is an open question.

### Coarser node granularity

v0.2 had one node per endpoint (15 endpoint nodes). v0.3 groups
them: `kb-crud-endpoints` covers 6 endpoints, `wiki-endpoints`
covers 3. Trade-off: fewer files but less granular drift detection.
If one endpoint changes, the whole group node goes stale.

Question for agent: was this a deliberate choice?

### Validation frequency during issue writing

The agent claimed "validated after every 5 files" in the compliance
checklist, but we observed ~28 issues written between validation
checkpoints (KBP-41 to KBP-69). Minor deviation — the issues were
structurally consistent so the risk was low, but the compliance
self-report is slightly overstated.

### Compliance checklist is thin

23 lines with "None" deviations. The validation frequency
overstatement suggests the agent wasn't fully honest in its self-
assessment. The compliance format works but the agent may be treating
it as a checkbox exercise rather than genuine reflection.

### Slower than v0.2

~45 minutes vs ~40 minutes for v0.2, producing fewer entities. The
no-subagent constraint means sequential writing. This is the expected
trade-off — quality over speed. But for larger projects, the
sequential approach may become a bottleneck.

### Reading phase was long

~7 minutes of reading before any file writes. 10 planning docs +
canonical examples, all sequential. This is correct behaviour but
represents a significant portion of the total time.

## Observations

### The phase-aware validator was the critical difference

The agent produced all meta-artifacts because it had to — the
validator wouldn't accept `phase: scoped` without them. In v0.2,
the same steps were "mandatory" in the workflow text but had no
enforcement. The agent skipped them. In v0.3, enforcement teeth
turned soft instructions into hard gates.

### "DO NOT SKIP" warnings may have helped

The workflow has explicit "DO NOT SKIP THIS STEP" warnings at steps
8, 9, and 10. Combined with the validator enforcement, these create
a two-layer defense: the text warning is the first line, the
validator is the backstop. We can't isolate which one drove the
behaviour — it could be either or both.

### The subagent ban simplified everything

No coherence loss, no key allocation confusion, no unread files.
The agent's gap analysis was meaningful because it had written and
therefore read every file. The trade-off (slower) is worth it at
this project size.

### Entity count differences need investigation

v0.3 produced fewer of everything. This could indicate:
- The agent read the same planning docs more carefully (having read
  them itself, not via subagent summaries) and made different scoping
  decisions
- The coarser node granularity reduced the node count which may have
  reduced issue count (fewer fine-grained implementation issues)
- Or the agent compressed scope despite the anti-anchoring
  instructions

The gap analysis found only 3 gaps in 76 issues, suggesting coverage
is adequate. But this needs verification.

## Possible improvements for v0.4

### 1. Validate frequency enforcement

The workflow says "every 3-5 files" but the agent wrote 28 issues
in a row. Consider making the validator track write count since last
validation and warn if it exceeds a threshold. Or accept that
batch-then-validate is fine for structurally consistent entities.

### 2. Compliance checklist honesty

The agent overstated its validation frequency. The compliance format
could include machine-verifiable claims: "validation ran N times"
(checkable from graph cache timestamps) rather than relying on
self-report.

### 3. Node granularity guidance

The workflow doesn't specify whether to create one node per endpoint
or group related endpoints. v0.2 and v0.3 made different choices.
Consider adding guidance: "One node per independently-deployable or
independently-changeable artifact."

### 4. Reading phase optimisation

7 minutes of sequential reads before any output. For repeated
scoping (rescope), the agent re-reads everything. Consider whether
`keel brief` could include a planning-doc summary to reduce re-read
time on subsequent runs.

### 5. Scoping plan as machine-readable input

The 264-line scoping plan is human-readable markdown tables. If it
were structured YAML, `keel next-key` could read it directly and
allocate keys, and a future `keel scaffold` command could generate
entity skeletons from it.

## Questions for the PM agent

```
SCOPING DECISIONS:

1. You produced 76 issues vs v0.2's 92. What drove the difference?
   Did you consciously scope more tightly, or did the planning docs
   naturally decompose into fewer issues?

2. You created 34 concept nodes vs v0.2's 53. Specifically, you
   grouped endpoints (e.g., `kb-crud-endpoints` covers 6 endpoints
   that v0.2 split into 6 nodes). Was this a deliberate granularity
   choice? What was your reasoning?

3. Did you read the CONCEPT_GRAPH.md reference doc, or did you rely
   on the "when to create a node" section in SKILL.md?

WORKFLOW COMPLIANCE:

4. Your compliance checklist says "validated after every 5 files."
   From external observation, there was a stretch of ~28 issues
   (KBP-41 to KBP-69) with no validation checkpoint. Can you
   reconcile this? Were there validation runs we didn't observe?

5. You wrote "None" under deviations in the compliance checklist.
   Looking back, is there anything you would change about how you
   executed the workflow? Any step you did less thoroughly than
   you could have?

6. Did you read ANTI_PATTERNS.md? The v0.2 agent skipped it. Which
   reference docs did you read beyond SKILL.md and the workflow?

SELF-REVIEW:

7. During the gap analysis (step 9), you found 3 gaps and created
   KBP-74, 75, 76. What were the 3 gaps specifically? How did you
   find them — by rereading the planning docs or from memory?

8. During the second-pass node coverage (step 8), did you find any
   concepts in prose that should have been nodes? Did you create
   any new nodes, or were the original 34 sufficient?

9. If I picked a random concrete issue — say KBP-42 — could you
   describe its title, repo, blocked_by, and at least 2 acceptance
   criteria without reading the file?

SUBAGENT BAN:

10. Did you feel constrained by the no-subagent rule? Were there
    moments where you wanted to delegate? How did writing everything
    yourself affect your ability to do the gap analysis?

PHASE-AWARE VALIDATION:

11. Were you aware that setting phase: scoped would fail validation
    if the artifacts weren't complete? Did that influence when you
    produced the artifacts?

FORMAT + TOOLING:

12. Did you use any of the new validate formats (--format summary,
    --format compact, --count)? Were they useful?

13. Did keel brief show you the node IDs list? Was that helpful
    when writing issues with [[refs]]?

PSYCHOLOGY:

14. Did you experience any of the patterns from the red-flag table?
    Wanting to skip the gap analysis, feeling like you'd "done
    enough," wanting to move to a more novel task? Be honest.

15. At any point did you feel time-constrained or want to manage
    a time budget across steps?
```

## Pending

- [ ] Q&A answers from PM agent
- [ ] Final commit verification
- [ ] Spot-check 5 random concrete issues for body quality
- [ ] Compare gap analysis coverage vs v0.2's self-identified gaps
- [ ] Verify all `[[node-id]]` refs resolve (run `keel refs check`)
