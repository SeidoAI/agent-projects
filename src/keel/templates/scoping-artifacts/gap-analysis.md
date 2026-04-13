# Gap analysis

<!-- status: incomplete -->

After all entities are written and validation passes, reread every
planning doc and map each deliverable to a covering issue.

**Each row must map ONE deliverable to ONE issue.** Do not group
deliverables or use issue ranges. If an issue covers multiple
deliverables, it appears in multiple rows.

## Planning doc → project coherence

### [filename].md
| Section | Deliverable | Covering issue | Status |
|---|---|---|---|
| §X.Y | [one specific deliverable] | [one issue key] | Covered / **Gap** |

## Planning doc internal coherence

List any contradictions between planning docs.

## Project self-coherence

- Issues with 0 node refs: _
- Nodes with only 1 referrer: _
- Sessions with 0 issues: _
- Dependency cycles: none / _

## Gaps found and resolved

| Gap | Resolution |
|---|---|
| [deliverable] | Created [KEY], added to [epic] |

When complete, replace `<!-- status: incomplete -->` with
`<!-- status: complete -->`.
