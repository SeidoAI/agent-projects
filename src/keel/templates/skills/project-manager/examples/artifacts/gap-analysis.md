# Gap analysis — kb-pivot initial scoping

## Planning doc → project coherence

### api-spec.md
| Deliverable | Issue | Status |
|---|---|---|
| KB CRUD (6 endpoints) | SEI-9 | Covered |
| Unified mutation (9 op types) | SEI-10 | Covered |
| Wiki endpoints (5) | SEI-11 | Covered |
| Upload endpoints (4) | SEI-21 | **Added after gap analysis** |
| Chat session updates (3) | SEI-22 | **Added after gap analysis** |
| Billing middleware | SEI-12 | Covered |

### infra-spec.md
| Deliverable | Issue | Status |
|---|---|---|
| GCS bucket + Terraform | SEI-6 | Covered |
| Agent Cloud Run provisioning | SEI-23 | **Added after gap analysis** |
| Neo4j decommission | SEI-7 | Covered |

## Planning doc internal coherence

### Inconsistencies found
1. **SSE event types:** overview-pivot-plan.md §2 lists 7 event
   types; agent-spec.md references "see §5.9" without restating.
   If either changes, the other silently drifts. → Created
   `[[sse-event-model]]` concept node to track this.

2. **Firestore schema fields:** transition-spec.md §7.1 lists
   specific user fields; architecture.md §2.7 references "user
   soft-delete fields" without listing. → Noted in SEI-12 body.

## Project self-coherence

- Issues with 0 node refs: **0** (all resolved in second-pass)
- Nodes with only 1 referrer: **1** (`gcs-bucket` — only SEI-6).
  Acceptable — infra nodes are naturally single-issue.
- Sessions with 0 issues: **0**
- Dependency cycles: **none**
