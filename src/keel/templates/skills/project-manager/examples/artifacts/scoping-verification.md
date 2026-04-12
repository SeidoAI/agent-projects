# Scoping verification — storage-adapter-impl

Maps planning doc sections to keel project entities.

| Planning doc | Section | Mapped to | Status |
|---|---|---|---|
| architecture.md | §2.1 StorageAdapter | [[storage-adapter]] + SEI-8 | Covered |
| architecture.md | §2.2 GCS bucket config | [[gcs-bucket]] + SEI-6 | Covered |
| architecture.md | §2.3 Firestore schema | SEI-9 (requirements) | Covered |
| api-spec.md | §3.1 KB CRUD endpoints | SEI-9 | Covered |
| api-spec.md | §3.4 Mutation endpoint | SEI-10 | Covered |
| api-spec.md | §3.x Upload endpoints | **GAP** — no issue | **Missing** |
| infra-spec.md | §6.3 Agent Cloud Run | **GAP** — no issue | **Missing** |

## Gaps identified
- Upload endpoints (4 endpoints) — need new issue under backend epic
- Agent Cloud Run provisioning — need new issue under infra epic

## Out of scope (with justification)
- Neo4j decommission (P14) — deferred until new system is stable
