# Compliance checklist — initial scoping

<!-- status: complete -->

## Validation checkpoints

| Checkpoint | Files written since last | Error count | Clean? |
|---|---|---|---|
| After 12 nodes | 12 | 2 (bidi/related) | no → fixed |
| After KBP-1 to KBP-8 (epics) | 8 | 0 | yes |
| After KBP-9 to KBP-16 (issues) | 8 | 3 (body/no_stop_and_ask) | no → fixed |
| After KBP-17 to KBP-25 (issues) | 9 | 0 | yes |
| After 8 sessions | 16 (session.yaml + plan.md) | 0 | yes |

## Quality calibration checkpoints

| After issue | First-3 avg chars | Last-3 avg chars | Rewrites? |
|---|---|---|---|
| KBP-25 | 2,410 | 2,380 | no |

## Key allocation

| Command | Keys allocated | Range |
|---|---|---|
| `keel next-key --type issue --count 25` | 25 | SEI-1 to SEI-25 |

## UUID allocation

| Command | Count |
|---|---|
| `keel uuid --count 45` | 45 |

## File counts

| Entity type | Count | Directory |
|---|---|---|
| Concept nodes | 12 | graph/nodes/ |
| Epic issues | 8 | issues/ |
| Concrete issues | 25 | issues/ |
| Sessions | 8 | sessions/ |
| Session plans | 8 | sessions/*/plan.md |

## Workflow steps completed

| Step | Done? | Notes |
|---|---|---|
| 1. Run keel brief | Yes | |
| 2. Read all planning docs | Yes | Read 10 files (~8,000 lines) |
| 3. Read canonical examples | Yes | 6 examples |
| 4. Write scoping plan | Yes | plans/artifacts/scoping-plan.md |
| 5. Allocate IDs + UUIDs | Yes | 25 keys, 45 UUIDs |
| 6. Write files | Yes | nodes → epics → issues → sessions |
| 7. Validation cycle | Yes | 5 checkpoints, 5 errors fixed |
| 8. Second-pass node coverage | Yes | Found 4 missing nodes |
| 9. Gap analysis | Yes | 2 gaps found and resolved |
| 10. Meta-artifacts | Yes | |
| 11. Final validation | Yes | 0 errors |
| 12. Phase advance + commit | Yes | phase: scoped |

## Deviations

### Node creation (step 8 second-pass)
Initially created 8 nodes. The second-pass found 4 concepts
(`config-json`, `sse-event-model`, `approval-flow`,
`chat-session-schema`) appearing in 3+ issue bodies as prose. Created
the nodes and replaced prose with `[[refs]]`. Resolved.
