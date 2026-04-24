import { ChevronLeft, ChevronRight, FileText, GitBranch, Layers } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import type { Referrer } from "@/lib/api/endpoints/nodes";

interface NodeReverseRefsProps {
  referrers: Referrer[];
  projectId: string;
  pageSize?: number;
}

const ICONS = {
  issue: FileText,
  node: Layers,
  session: GitBranch,
} as const;

function referrerHref(pid: string, r: Referrer): string {
  switch (r.kind) {
    case "issue":
      return `/p/${pid}/issues/${r.id}`;
    case "node":
      return `/p/${pid}/nodes/${r.id}`;
    case "session":
      return `/p/${pid}/sessions/${r.id}`;
  }
}

export function NodeReverseRefs({ referrers, projectId, pageSize = 10 }: NodeReverseRefsProps) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(referrers.length / pageSize));
  const clamped = Math.min(page, pageCount - 1);
  const start = clamped * pageSize;
  const slice = referrers.slice(start, start + pageSize);

  return (
    <section aria-labelledby="node-reverse-refs-heading" className="space-y-2">
      <h2 id="node-reverse-refs-heading" className="text-sm font-semibold text-foreground">
        Referenced by ({referrers.length})
      </h2>
      {referrers.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          This node is not yet referenced by any issue, node, or session.
        </p>
      ) : (
        <>
          <ul className="space-y-1.5">
            {slice.map((r) => {
              const Icon = ICONS[r.kind];
              return (
                <li
                  key={`${r.kind}:${r.id}`}
                  className="flex items-center gap-2 text-sm"
                  data-referrer-id={r.id}
                  data-referrer-kind={r.kind}
                >
                  <Icon className="h-4 w-4 text-muted-foreground" aria-label={r.kind} />
                  <Link
                    to={referrerHref(projectId, r)}
                    className="underline decoration-dotted hover:decoration-solid"
                  >
                    {r.id}
                  </Link>
                </li>
              );
            })}
          </ul>
          {pageCount > 1 ? (
            <div className="flex items-center gap-2 pt-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={clamped === 0}
                aria-label="Previous page"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <span className="text-xs text-muted-foreground">
                Page {clamped + 1} of {pageCount}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                disabled={clamped >= pageCount - 1}
                aria-label="Next page"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
