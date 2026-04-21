# Gap analysis — initial scoping

<!-- status: complete -->

## Planning doc → project coherence

### api-spec.md
| Section | Deliverable | Covering issue | Status |
|---|---|---|---|
| §2.1 | POST /kb (create KB) | SEI-9 | Covered |
| §2.2 | GET /kb (list KBs) | SEI-9 | Covered |
| §2.3 | GET /kb/{id} | SEI-9 | Covered |
| §2.4 | PATCH /kb/{id} | SEI-9 | Covered |
| §2.5 | DELETE /kb/{id} | SEI-9 | Covered |
| §3.1 | POST /graph/mutate | SEI-10 | Covered |
| §3.2 | GET /graph/overview | SEI-10 | Covered |
| §4.1 | GET /wiki/{path} | SEI-11 | Covered |
| §4.2 | PUT /wiki/{path} | SEI-11 | Covered |
| §5.1 | POST /uploads | — | **Gap → created SEI-21** |
| §5.2 | GET /uploads/{id} | — | **Gap → created SEI-21** |
| §6.1 | Billing gate middleware | SEI-12 | Covered |

### infra-spec.md
| Section | Deliverable | Covering issue | Status |
|---|---|---|---|
| §1.1 | GCS bucket Terraform module | SEI-6 | Covered |
| §1.2 | IAM bindings for Cloud Run | SEI-6 | Covered |
| §2.1 | Neo4j module removal | SEI-7 | Covered |
| §3.1 | Agent Cloud Run service | — | **Gap → created SEI-23** |

## Planning doc internal coherence

### Inconsistencies found
1. **SSE event types:** overview-pivot-plan.md §2 lists 7 event
   types; agent-spec.md references "see §5.9" without restating.
   If either changes, the other silently drifts. → Created
   `[[sse-event-model]]` concept node to track this.

## Project self-coherence

- Issues with 0 node refs: **0** (all resolved in second-pass)
- Nodes with only 1 referrer: **1** (`gcs-bucket` — only SEI-6).
  Acceptable — infra nodes are naturally single-issue.
- Sessions with 0 issues: **0**
- Dependency cycles: **none**

## Gaps found and resolved

| Gap | Resolution |
|---|---|
| Upload endpoints (api-spec §5) | Created SEI-21, added to Epic 3 |
| Chat session updates (api-spec §5.3) | Created SEI-22, added to Epic 3 |
| Agent Cloud Run provisioning (infra-spec §3) | Created SEI-23, added to Epic 1 |
