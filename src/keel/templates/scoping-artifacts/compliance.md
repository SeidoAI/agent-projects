# Compliance checklist

<!-- status: incomplete -->

## Validation checkpoints

Record every `keel validate` run during file writing. Each row is one
checkpoint. No gap between checkpoints should exceed 10 files.

| Checkpoint | Files written since last | Error count | Clean? |
|---|---|---|---|
| After [KEY range] | N | N | yes/no |

## Quality calibration checkpoints

Record every calibration (every 20 concrete issues). Compare your
first 3 concrete issues against your last 3 at each checkpoint.

| After issue | First-3 avg chars | Last-3 avg chars | Rewrites? |
|---|---|---|---|
| [KEY] | N | N | yes/no — [keys rewritten] |

## Key allocation

| Command | Keys allocated | Range |
|---|---|---|
| `keel next-key --type issue --count N` | N | KEY-X to KEY-Y |

## UUID allocation

| Command | Count |
|---|---|
| `keel uuid --count N` | N |

## File counts

| Entity type | Count | Directory |
|---|---|---|
| Concept nodes | _ | nodes/ |
| Epic issues | _ | issues/ |
| Concrete issues | _ | issues/ |
| Sessions | _ | sessions/ |
| Session plans | _ | sessions/*/plan.md |

## Workflow steps completed

| Step | Done? | Notes |
|---|---|---|
| 1. Run keel brief | | |
| 2. Read all planning docs | | |
| 3. Read canonical examples | | |
| 4. Write scoping plan | | |
| 5. Allocate IDs + UUIDs | | |
| 6. Write files (nodes → epics → issues → sessions) | | |
| 7. Validation cycle | | |
| 8. Second-pass node coverage | | |
| 9. Gap analysis | | |
| 10. Meta-artifacts | | |
| 11. Final validation | | |
| 12. Phase advance + commit | | |

## Deviations

List any deviations from the workflow and explain why.

When complete, replace `<!-- status: incomplete -->` with
`<!-- status: complete -->`.
