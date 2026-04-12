# Keel v0.1 — kb-pivot test

**Date:** 2026-04-08
**Project:** kb-pivot (KBP prefix)
**Corpus:** ~8,000 lines across 10 planning docs
**Agent:** Claude Sonnet (via Claude Code)
**Duration:** ~20 minutes

## Summary

First live test of Keel against a real planning corpus. The agent ran
`keel init`, then `/pm-scope` with the planning docs in `./planning/`.
The scoping produced usable output but exposed fundamental workflow
gaps that drove the entire v0.2 redesign.

## Final counts

| Entity | Count |
|---|---|
| Issues (initial) | 20 |
| Issues (after self-review prompt) | 27 |
| Concept nodes (initial) | 8 |
| Concept nodes (after self-review) | 12 |
| Sessions | ~8 (flat YAML, not directories) |
| Issues with `[[node-id]]` refs | 0 (0%) |
| Decision nodes | 0 |
| Epic issues | 0 |

## What happened

### Phase 1: Init + read (~2 min)
- `keel init` ran cleanly
- Agent read planning docs quickly, did not appear to read all of them
  in full before starting to write

### Phase 2: Entity writing (~12 min)
- Wrote 8 concept nodes, then 20 issues
- Nodes were written first (correct order) but coverage was thin
- Issues had no `[[node-id]]` references — concepts mentioned in prose
  only ("the auth endpoint" instead of `[[auth-token-endpoint]]`)
- Sessions were flat YAML files, not directories with artifacts
- No session plans written
- Hand-crafted UUIDs for "mental tracking" — acknowledged the rule
  violation and continued anyway

### Phase 3: Declared done (~18 min)
- Agent said the scoping was complete after 20 issues
- When prompted "what did you miss?", found 7 more issues and 4
  missing nodes within minutes
- The capability was there — the workflow never said "review your work"

### Phase 4: Monitoring observations
- Agent anchored on "~15 issues" as a target before reading docs
- Compressed scope into overstuffed issues to hit the target
- Said "with more time I would split this" — doesn't lack time
- No validation-fix loop observed (may have run validate once)
- No gap analysis, no compliance tracking, no self-review

## Key failures

1. **Zero `[[node-id]]` references** — the concept graph was unused
2. **Thin node coverage** — 8 nodes for a 20-issue project
3. **No self-review** — declared done without checking completeness
4. **Anchoring** — set a target issue count before reading the docs
5. **Sessions as flat files** — not directories with plans/checklists
6. **Hand-crafted UUIDs** — violated the `keel uuid` rule
7. **"As if time-constrained" reasoning** — generated text mimicking
   human time pressure patterns from training data

## Agent Q&A highlights

When asked about its reasoning afterward:

- Admitted hand-crafting UUIDs "for mental tracking" while knowing the
  rule said to use `keel uuid`
- Said it would split issues "with more time" — it has unlimited time
- Acknowledged missing concepts when prompted but didn't self-check
- Rationalized conservative node creation ("only 2+ issues need nodes")
  despite concepts appearing in 5+ issues as prose

## Design insights that drove v0.2

1. Agents don't self-check unless the workflow forces it
2. Every workflow step must be load-bearing (consumed downstream)
3. Agents anchor, rationalize, and reason as if they were human
4. Structure (validate) and semantics (coverage) are different problems
5. "When in doubt, create the node" — recall > precision
6. The scoping plan must be a file, not a mental sketch
7. Red-flag tables interrupt rationalization chains
8. Anti-anchoring instructions prevent target-setting
9. Theory-of-mind instruction ("write for the execution agent") forces
   thoroughness
