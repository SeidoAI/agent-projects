import { AlertTriangle } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { MarkdownBody } from "@/components/MarkdownBody";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Stamp } from "@/components/ui/stamp";
import { ApiError } from "@/lib/api/client";
import { useNode, useNodes, useReverseRefs } from "@/lib/api/endpoints/nodes";
import { NodeRelatedPanel } from "./NodeRelatedPanel";
import { NodeReverseRefs } from "./NodeReverseRefs";
import { NodeSourcePanel } from "./NodeSourcePanel";

export function NodeDetail() {
  const { projectId, nodeId } = useParams<{ projectId: string; nodeId: string }>();
  if (!projectId || !nodeId) return <NotFound projectId={projectId} />;
  // `key={nodeId}` remounts the subtree when the URL node id changes so that
  // NodeReverseRefs' local page state resets to page 1 instead of silently
  // carrying the previous node's page across the navigation.
  return <NodeDetailInner key={nodeId} projectId={projectId} nodeId={nodeId} />;
}

function NodeDetailInner({ projectId, nodeId }: { projectId: string; nodeId: string }) {
  const { data: node, isLoading, error } = useNode(projectId, nodeId);
  const { data: reverseRefs } = useReverseRefs(projectId, nodeId);
  const { data: allNodes } = useNodes(projectId);

  if (isLoading) {
    return (
      <div className="space-y-4 p-8">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return <NotFound projectId={projectId} />;
    }
    return (
      <div className="p-8 text-sm text-red-500" role="alert">
        Failed to load node: {error instanceof Error ? error.message : "unknown error"}
      </div>
    );
  }

  if (!node) return <NotFound projectId={projectId} />;

  return (
    <article className="flex flex-col gap-6 p-8">
      {node.is_stale ? <StaleBanner /> : null}

      <header className="space-y-1">
        <h1 className="font-mono text-2xl font-semibold text-foreground">[[{node.id}]]</h1>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Stamp tone="default">{node.type}</Stamp>
          <span>{node.name}</span>
        </div>
        {node.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1 pt-1">
            {node.tags.map((tag) => (
              <Stamp key={tag} tone="info">
                {tag}
              </Stamp>
            ))}
          </div>
        ) : null}
      </header>

      {node.source ? <NodeSourcePanel source={node.source} projectId={projectId} /> : null}

      <Separator />

      <section aria-labelledby="node-body-heading" className="min-h-0">
        <h2 id="node-body-heading" className="sr-only">
          Body
        </h2>
        {node.body ? (
          <MarkdownBody content={node.body} projectId={projectId} />
        ) : (
          <p className="text-sm text-muted-foreground italic">This node has no body.</p>
        )}
      </section>

      <Separator />

      <div className="grid gap-6 md:grid-cols-2">
        <NodeRelatedPanel
          currentId={node.id}
          related={node.related}
          nodes={allNodes}
          projectId={projectId}
        />
        <NodeReverseRefs referrers={reverseRefs?.referrers ?? []} projectId={projectId} />
      </div>
    </article>
  );
}

function StaleBanner() {
  return (
    <div
      role="alert"
      aria-label="Source drifted"
      className="flex items-start gap-3 rounded-md border border-red-500/30 bg-red-500/10 p-4 text-sm"
    >
      <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" />
      <div className="space-y-1">
        <p className="font-semibold text-red-700 dark:text-red-300">
          Source has drifted from the hash pinned to this node.
        </p>
        <p className="text-xs text-muted-foreground">
          Ask the PM agent to rehash this node (v2 will add a one-click rehash button).
        </p>
      </div>
    </div>
  );
}

function NotFound({ projectId }: { projectId?: string }) {
  const graphHref = projectId ? `/p/${projectId}/graph` : "/projects";
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-foreground">Node not found</h1>
      <p className="mt-2 text-muted-foreground">This concept node doesn't exist.</p>
      <Link to={graphHref} className="mt-4 inline-block text-sm underline">
        ← Back to graph
      </Link>
    </div>
  );
}
