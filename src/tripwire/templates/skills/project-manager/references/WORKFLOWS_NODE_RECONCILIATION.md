# Workflow: Concept-Freshness / Node Reconciliation

Concept nodes carry a `source` block — `repo`, `path`, `branch`,
`content_hash` — pinning each node to a specific revision of the
code it describes. The hash is a provenance contract: it lets the
graph age cleanly against a moving source repo instead of quietly
diverging. This workflow closes the loop — it takes nodes flagged
as stale, walks each one, and resolves the divergence to a known
state: refreshed, accepted, or deleted.

The `concept-freshness` workflow lives in `workflow.yaml` with three
statuses: `detected → reviewing → reconciled`. Trigger is the
overseer signal `signal.stale_node_count_high`; the `code-review`
workflow's `node-reconcile` station also cross-links into
`detected`.

## When this workflow fires

Two upstream sources:

1. **`signal.stale_node_count_high`** from `pm-monitor`. The monitor
   tick scans `nodes/` and counts `v_freshness` failures (each node
   whose stored `content_hash` no longer matches the SHA256 of its
   `source.path` on `source.branch`). When the count crosses the
   `monitor.stale_node_count_high` threshold (default 5) the signal
   fires and dispatch routes to `concept-freshness.detected`. See
   `MONITOR_CRITERIA.md`.
2. **`code-review.node-reconcile → concept-freshness.detected,
   kind: triggers`**. After a session merges, the touched-source
   rehash on `node-reconcile` typically yields one or more refreshed
   `content_hash` values; the cross-link kicks the project-wide
   freshness scan so unrelated stale nodes get picked up while the
   PM is already in reconciliation context. See
   `WORKFLOWS_CODE_REVIEW.md`.

The workflow runs PM-driven. Subagent dispatch is permitted but the
default is inline — reconciliation decisions are judgment calls
that benefit from the PM's full context.

## Walking the staleness queue (`reviewing`)

The PM lists every node currently failing `v_freshness`:

```bash
tripwire validate --json | jq '.errors[] | select(.code == "v_freshness")'
```

For each result the PM reads:

- The node file (`nodes/<id>.yaml`) — frontmatter + body.
- The current source (`source.path` on `source.branch`) — the file
  the node points at, as it stands on the latest commit.

Three outcomes per node, decided in order:

1. **Refresh** — source moved, body still describes the right thing.
   Default outcome.
2. **Accept divergence** — source moved, body is intentionally
   describing the older or aspirational design.
3. **Delete** — source has gone away or the concept itself is
   obsolete.

### Worked example

`nodes/file-watcher.yaml` has `source.path:
src/tripwire/_internal/watcher.py` and
`content_hash: sha256:abc…`. The current SHA of `watcher.py` is
`def…`. The PM reads both:

- The node body talks about a 100ms debounce.
- The current `watcher.py` debounces at 250ms and added a
  burst-mode coalescer.

This is a **refresh**: the body needs to mention 250ms and the
coalescer, and `content_hash` needs to bump to `def…`.

## Refresh

```bash
sha256sum src/tripwire/_internal/watcher.py
# → def7c1...  src/tripwire/_internal/watcher.py
```

Edit `nodes/file-watcher.yaml`:

- Update body sections that describe behaviour the source has
  changed.
- Update `source.content_hash` to the new SHA (`sha256:def7c1…`).
- Update `source.branch` if the node was pinned to a feature branch
  that has since merged.
- Bump `updated_at` to today.

Then `tripwire validate` — the `v_freshness` error for this node
should clear.

## Accept divergence

Rare. Used when the body is intentionally describing the older
design (because it's the contract the rest of the graph references)
or an aspirational design that the source hasn't caught up to.

In the body, append a `## Divergence` section that names what's
changed in the source and why the node body wasn't rewritten:

```markdown
## Divergence

As of 2026-05-04 the live `watcher.py` debounces at 250ms, not
100ms. The 100ms figure is preserved here because
`[[websocket-hub]]` and `[[event-emitter]]` reference it as the
contract; the divergence is tracked in issue SEI-87.
```

Update `source.content_hash` to the current source SHA — accepting
divergence still means re-pinning, otherwise the next freshness
scan re-fires the same alert. Bump `updated_at`.

## Delete

When the source file has been removed or the concept itself is no
longer meaningful:

1. `rm nodes/<id>.yaml`.
2. `tripwire refs reverse <id>` — list every node whose `related:`
   list includes the deleted id.
3. For each, edit out the dropped id from `related:`. The graph
   stays bidirectionally clean.
4. Validate.

If reverse-refs is non-trivial (the deleted node was central),
prefer accept-divergence over delete; deletion cascades are easy to
get wrong.

## Bidirectional `related:`

Every concept node's `related:` entries are bidirectional by
contract. If `nodes/a.yaml` lists `b` in `related:`, then
`nodes/b.yaml` must list `a`. The validator surfaces asymmetric
edges as warnings (`w_related_asymmetric`); reconciliation is the
right time to clean them up. See `VALIDATION.md` and `SKILL.md`.

When refresh adds a new related concept (because the rewritten body
now references something it didn't before), update both sides.

## Reaching `reconciled`

The terminal status. Exit conditions:

- Every node that was failing `v_freshness` at workflow entry has
  been refreshed, marked accept-divergence, or deleted.
- `tripwire validate` reports zero `v_freshness` errors.
- Reverse-ref cleanup committed for any deletions.

Commit convention: `reconcile: <node-list> after freshness scan`
or `reconcile: <node-list> after #<pr>` when triggered by a
specific merge. See `COMMIT_CONVENTIONS.md`.

## See also

- `SKILL.md` — PM agent entry point, `related:` bidirectional rule.
- `WORKFLOWS_CODE_REVIEW.md` — the cross-link source from
  `node-reconcile`.
- `MONITOR_CRITERIA.md` — `signal.stale_node_count_high` threshold
  and dispatch.
- `VALIDATION.md` — `v_freshness` and the related warning codes.
- `templates/skills/verification/` — checklist consulted when a
  refresh has to re-walk the source against acceptance criteria.
