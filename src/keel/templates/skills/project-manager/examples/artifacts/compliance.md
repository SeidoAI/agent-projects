# Compliance checklist — initial scoping

| Rule | Followed? | Notes |
|---|---|---|
| Read all planning docs in full | Yes | Read 10 files (~8,000 lines) |
| Run `keel brief` before writing | Yes | |
| Write scoping plan artifact before files | Yes | plans/artifacts/scoping-plan.md |
| Write nodes before issues | Yes | 12 nodes created first |
| Allocate keys via `keel next-key` | Yes | `--count 25` |
| Generate UUIDs via `keel uuid` | Yes | `--count 37` |
| Validate after every 3-5 files | Yes | 6 validation checkpoints |
| Create a node for every 2+ referenced concept | **Deviated** | Added 4 missing nodes in second-pass (step 8) |
| Write session plans for every session | Yes | 8 plans in sessions/*/plan.md |
| Run second-pass node check (step 8) | Yes | Found 4 missing nodes |
| Produce gap analysis (step 9) | Yes | 2 gaps found and resolved |
| Cross-reference planning docs (step 8.5) | Yes | All sections mapped |

## Deviations

### Node creation (step 8 second-pass)
Initially created 8 nodes. The second-pass in step 8 found 4
concepts (`config-json`, `sse-event-model`, `approval-flow`,
`chat-session-schema`) appearing in 3+ issue bodies as prose. Created
the nodes and replaced prose with `[[refs]]`. Resolved.
