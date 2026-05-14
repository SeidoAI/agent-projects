# Workflow: Concept-Freshness / Node Reconciliation

> **Compliance reminder.** `tripwire validate` is your accountability
> surface. Run it after every change. Exit code 0 → proceed. Non-zero
> → STOP and address findings. **You MUST NOT skip validation.**

Concept nodes pin a `source` (repo, path, branch, content_hash) so
the graph ages cleanly against a moving source repo. This workflow
closes the loop: stale nodes get walked and resolved as refreshed,
accepted, or deleted.

`concept-freshness` in `workflow.yaml` runs `detected → reviewing →
reconciled`. Triggered by `signal.stale_node_count_high`;
`code-review.node-reconcile` cross-links into `detected` too.

`concept-freshness` is reference-only — no executor coverage today.
The workflow's `status:` advancement is conventional (`detected →
reviewing → reconciled` recorded out of band); the load-bearing gate
is `tripwire validate` reporting zero `v_freshness` findings.

## When it fires

1. **`signal.stale_node_count_high`** from `pm-monitor` — count of
   `v_freshness` failures crosses `monitor.stale_node_count_high`
   (default 5). Dispatch → `concept-freshness.detected`. See
   `MONITOR_CRITERIA.md`.
2. **`code-review.node-reconcile → detected`** — after a session
   merges, the touched-source rehash usually refreshes a few hashes;
   the cross-link kicks a project-wide scan while the PM is already
   in reconciliation context. See `WORKFLOWS_CODE_REVIEW.md`.

PM-driven. Subagent dispatch allowed; default is inline (judgment
calls benefit from full context).

## Walking the queue (`reviewing`)

Run:

```bash
tripwire validate --format json | jq '.errors[] | select(.code == "v_freshness")'
```

For each result: read the node file (`nodes/<id>.yaml`) and the
current `source.path` content. Decide in order:

| Action | When |
|---|---|
| **Refresh** | Source moved, body still right. Default. |
| **Accept divergence** | Source moved, body intentionally describes the older / aspirational design. |
| **Delete** | Source gone, concept obsolete. |

**Example.** `file-watcher.yaml` points at `watcher.py`,
`content_hash: sha256:abc…`. Current SHA is `def…`. Body mentions a
100ms debounce; current code debounces at 250ms with a burst
coalescer. This is a **refresh**: body updated, hash bumped to
`def…`.

## Refresh

Run:

```bash
sha256sum src/tripwire/_internal/watcher.py
```

Edit the node file (`Edit` tool): update affected body sections, set
`source.content_hash` to the new SHA, update `source.branch` if it
moved, bump `updated_at`.

Run `tripwire validate`. Exit 0 → continue. Non-zero → STOP and fix.
`v_freshness` should clear for the touched node.

## Accept divergence

Rare. The body intentionally describes an older contract (because
the rest of the graph references it that way) or an aspirational
design the source hasn't caught up to.

Append a `## Divergence` body section naming what changed and why it
wasn't rewritten:

```markdown
## Divergence

As of 2026-05-04 `watcher.py` debounces at 250ms, not 100ms. 100ms
is preserved here because [[websocket-hub]] and [[event-emitter]]
reference it as the contract; tracked in SEI-87.
```

Update `source.content_hash` anyway — accepting still means
re-pinning, or the next scan re-fires. Run `tripwire validate`.

## Delete

1. `rm nodes/<id>.yaml`.
2. Run `tripwire refs reverse <id>` — find every node whose
   `related:` includes the deleted id.
3. Edit each (`Edit` tool) to drop the id (graph stays bidirectional).
4. Run `tripwire validate`. Exit 0 → done. Non-zero → STOP and fix.

If reverse-refs is non-trivial, prefer accept-divergence — deletion
cascades are easy to get wrong.

## Bidirectional `related:`

`a.related ⊇ {b}` ⟺ `b.related ⊇ {a}`. Validator warns
(`w_related_asymmetric`) on asymmetric edges; reconciliation is when
to clean them up. When a refresh adds a new related concept, update
both sides.

## Reaching `reconciled`

Exit conditions: every entry-time `v_freshness` failure handled
(refresh / accept / delete); `tripwire validate` reports zero
`v_freshness`; reverse-ref cleanup committed.

If any step fails: read the validator finding, fix the underlying
node, re-validate.

Commit: `reconcile: <node-list> after freshness scan` (or
`after #<pr>` when triggered by a merge). See `COMMIT_CONVENTIONS.md`.

## See also

- `SKILL.md` — PM entry point, bidirectional `related:` rule.
- `WORKFLOWS_CODE_REVIEW.md` — `node-reconcile` cross-link source.
- `MONITOR_CRITERIA.md` — `signal.stale_node_count_high` threshold.
- `VALIDATION.md` — `v_freshness` and related codes.
- `docs/WORKFLOW_ACTIONS.md` — every CLI command and transition.
