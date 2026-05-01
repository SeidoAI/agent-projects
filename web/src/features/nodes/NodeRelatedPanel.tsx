import { ArrowLeftRight, ArrowRight, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import type { NodeSummary } from "@/lib/api/endpoints/nodes";

interface NodeRelatedPanelProps {
  currentId: string;
  related: string[];
  nodes: NodeSummary[] | undefined;
  projectId: string;
}

interface RelatedEntry {
  id: string;
  bidirectional: boolean;
  known: boolean;
}

function classify(
  currentId: string,
  related: string[],
  nodes: NodeSummary[] | undefined,
): RelatedEntry[] {
  const byId = new Map((nodes ?? []).map((n) => [n.id, n] as const));
  return related.map((id) => {
    const other = byId.get(id);
    const bidirectional = other ? other.related.includes(currentId) : false;
    return { id, bidirectional, known: other !== undefined };
  });
}

export function NodeRelatedPanel({ currentId, related, nodes, projectId }: NodeRelatedPanelProps) {
  const entries = classify(currentId, related, nodes);

  return (
    <section aria-labelledby="node-related-heading" className="space-y-2">
      <h2 id="node-related-heading" className="text-sm font-semibold text-foreground">
        Related nodes ({related.length})
      </h2>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">No related nodes.</p>
      ) : (
        <ul className="space-y-1.5">
          {entries.map((entry) => (
            <li
              key={entry.id}
              className="flex items-center gap-2 text-sm"
              data-related-id={entry.id}
            >
              {entry.bidirectional ? (
                <ArrowLeftRight
                  className="h-4 w-4 text-emerald-500"
                  aria-label="bidirectional"
                  data-relation="bidirectional"
                />
              ) : entry.known ? (
                <ArrowRight
                  className="h-4 w-4 text-amber-500"
                  aria-label="one-sided"
                  data-relation="one-sided"
                />
              ) : (
                <TriangleAlert
                  className="h-4 w-4 text-red-500"
                  aria-label="missing"
                  data-relation="unknown"
                />
              )}
              <Link
                to={`/p/${projectId}/nodes/${entry.id}`}
                className="underline decoration-dotted hover:decoration-solid"
              >
                {entry.id}
              </Link>
              {!entry.bidirectional && entry.known ? (
                <span className="text-xs text-amber-500">one-sided</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
