import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";

import { MarkdownBody } from "@/components/MarkdownBody";
import { Stamp } from "@/components/ui/stamp";
import type { InboxItem } from "@/lib/api/endpoints/inbox";
import type { ReactFlowEdge, ReactFlowNode } from "@/lib/api/endpoints/graph";
import { useNode } from "@/lib/api/endpoints/nodes";

/**
 * Right-rail concept detail (KUI-104, spec §3.5 + amendment).
 *
 * Adopts the same visual language as `EntityPreviewDrawer` so the
 * graph rail reads as a "permanent open drawer": kind stamp +
 * Bricolage title, Instrument-Serif description, Markdown body,
 * references chip strip. Plus three KUI-104 amendments:
 *
 * - **Version metadata**: when the node has a `source.content_hash`,
 *   surface an abbreviated version stamp.
 * - **Inbox cross-links**: open inbox entries that reference this
 *   node show as a chip strip with a count + click target.
 * - **"open in drawer →"**: when the node has a long body the
 *   caller can offer a hand-off to the larger preview surface.
 */
export interface GraphRailProps {
  projectId: string;
  /** Currently-focused concept; falsy when no selection. */
  node: ReactFlowNode | null;
  /** Edges incident to the focus, used to render the related list. */
  incident: ReactFlowEdge[];
  /** All graph nodes, used to resolve neighbour labels. */
  allNodes: ReactFlowNode[];
  /** Inbox entries referencing this node, sorted newest-first. */
  referencingInbox: InboxItem[];
  onSelectNeighbour: (id: string) => void;
  onOpenInboxEntry?: (entryId: string) => void;
}

const VERSION_PREFIX = "sha256:";

export function GraphRail({
  projectId,
  node,
  incident,
  allNodes,
  referencingInbox,
  onSelectNeighbour,
  onOpenInboxEntry,
}: GraphRailProps) {
  const { data: detail, isLoading } = useNode(projectId, node?.id ?? "");

  if (!node) {
    return (
      <aside
        data-testid="graph-rail"
        className="flex w-80 shrink-0 flex-col items-start gap-2 border-(--color-edge) border-l bg-(--color-paper) px-5 py-4"
      >
        <p className="font-serif text-[14px] italic text-(--color-ink-3)">
          No concept selected. Click a node to inspect it.
        </p>
      </aside>
    );
  }

  const label = String(node.data?.label ?? node.id);
  const kind = String(node.data?.type ?? "concept");
  const stale = detail?.is_stale ?? node.data?.status === "stale";
  const version =
    detail?.source?.content_hash &&
    detail.source.content_hash.startsWith(VERSION_PREFIX)
      ? detail.source.content_hash.slice(VERSION_PREFIX.length, VERSION_PREFIX.length + 7)
      : null;
  const lastTouched = detail ? null : null; // TODO(v0.8.x): wire reverse-refs/last-session-id when service exposes it

  const neighbours = incident
    .map((e) => {
      const otherId = e.source === node.id ? e.target : e.source;
      const other = allNodes.find((n) => n.id === otherId);
      if (!other) return null;
      return {
        id: otherId,
        label: String(other.data?.label ?? otherId),
        relation: e.relation,
      };
    })
    .filter((x): x is { id: string; label: string; relation: string } => x !== null);

  return (
    <aside
      data-testid="graph-rail"
      className="flex w-80 shrink-0 flex-col gap-4 overflow-y-auto border-(--color-edge) border-l bg-(--color-paper) px-5 py-4"
    >
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Stamp tone={stale ? "tripwire" : "default"} variant="status">
            {kind}
          </Stamp>
          {stale ? (
            <Stamp tone="tripwire" variant="status">
              stale
            </Stamp>
          ) : null}
        </div>
        <h2 className="font-sans font-semibold text-[20px] text-(--color-ink) leading-tight tracking-[-0.01em]">
          [[{label}]]
        </h2>
        {detail?.description ? (
          <p className="font-serif text-[14px] text-(--color-ink-2) leading-snug">
            {detail.description}
          </p>
        ) : null}
        {version ? (
          <div className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
            version · v{version}
            {lastTouched ? ` · last touched by ${lastTouched}` : null}
          </div>
        ) : null}
      </header>

      {detail?.body && detail.body.trim() ? (
        <div className="border-(--color-edge) border-t pt-3">
          <MarkdownBody content={detail.body} projectId={projectId} compact />
        </div>
      ) : null}

      {neighbours.length > 0 ? (
        <div className="flex flex-col gap-2 border-(--color-edge) border-t pt-3">
          <div className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
            related
          </div>
          <ul className="flex flex-col gap-1">
            {neighbours.map((n) => (
              <li key={`${n.id}:${n.relation}`}>
                <button
                  type="button"
                  onClick={() => onSelectNeighbour(n.id)}
                  className="flex w-full items-center justify-between gap-2 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) px-2 py-1.5 text-left text-[12px] text-(--color-ink-2) transition-colors hover:bg-(--color-paper-3)"
                >
                  <span className="truncate">[[{n.label}]]</span>
                  <span className="shrink-0 font-mono text-[9.5px] text-(--color-ink-3) uppercase tracking-[0.06em]">
                    {n.relation}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {referencingInbox.length > 0 ? (
        <div className="flex flex-col gap-2 border-(--color-edge) border-t pt-3">
          <div className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
            inbox · {referencingInbox.length}
          </div>
          <ul className="flex flex-col gap-1">
            {referencingInbox.map((entry) => (
              <li key={entry.id}>
                <button
                  type="button"
                  onClick={() => onOpenInboxEntry?.(entry.id)}
                  className="flex w-full items-start justify-between gap-2 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) px-2 py-1.5 text-left text-[12px] text-(--color-ink-2) transition-colors hover:bg-(--color-paper-3)"
                >
                  <span className="min-w-0 truncate">{entry.title}</span>
                  <Stamp
                    tone={entry.bucket === "blocked" ? "rule" : "default"}
                    variant="status"
                  >
                    {entry.bucket}
                  </Stamp>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {detail && (detail.body?.length ?? 0) > 600 ? (
        <Link
          to={`/p/${projectId}/nodes/${node.id}`}
          className="inline-flex items-center gap-1 font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em] hover:text-(--color-ink)"
        >
          <ExternalLink className="h-3 w-3" aria-hidden /> open full
        </Link>
      ) : null}

      {isLoading ? (
        <p className="font-serif text-[12px] italic text-(--color-ink-3)">loading…</p>
      ) : null}
    </aside>
  );
}
