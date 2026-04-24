import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Link } from "react-router-dom";

import type { IssueReference } from "@/lib/api/endpoints/issues";

interface IssueRefsPanelProps {
  refs: IssueReference[];
  projectId: string;
}

function refHref(pid: string, ref: IssueReference): string | null {
  if (ref.resolves_as === "dangling") return null;
  const prefix = ref.resolves_as === "issue" ? "issues" : "nodes";
  return `/p/${pid}/${prefix}/${ref.ref}`;
}

function RefIcon({ ref }: { ref: IssueReference }) {
  if (ref.resolves_as === "dangling") {
    return (
      <XCircle className="h-4 w-4 text-red-500" aria-label="dangling" data-status="dangling" />
    );
  }
  if (ref.is_stale) {
    return (
      <AlertTriangle className="h-4 w-4 text-amber-500" aria-label="stale" data-status="stale" />
    );
  }
  return (
    <CheckCircle2
      className="h-4 w-4 text-emerald-500"
      aria-label="resolved"
      data-status="resolved"
    />
  );
}

export function IssueRefsPanel({ refs, projectId }: IssueRefsPanelProps) {
  return (
    <section aria-labelledby="issue-refs-heading" className="space-y-2">
      <h2 id="issue-refs-heading" className="text-sm font-semibold text-foreground">
        References ({refs.length})
      </h2>
      {refs.length === 0 ? (
        <p className="text-sm text-muted-foreground">No references.</p>
      ) : (
        <ul className="space-y-1.5">
          {refs.map((ref) => {
            const href = refHref(projectId, ref);
            return (
              <li
                key={ref.ref}
                className="flex items-center gap-2 text-sm"
                data-ref-token={ref.ref}
              >
                <RefIcon ref={ref} />
                {href ? (
                  <Link
                    to={href}
                    className="text-foreground underline decoration-dotted hover:decoration-solid"
                  >
                    {ref.ref}
                  </Link>
                ) : (
                  <span className="text-muted-foreground">{ref.ref}</span>
                )}
                {ref.resolves_as === "dangling" ? (
                  <span className="text-xs text-red-500">dangling</span>
                ) : ref.is_stale ? (
                  <span className="text-xs text-amber-500">stale</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
