import { MarkdownBody } from "@/components/MarkdownBody";
import { Skeleton } from "@/components/ui/skeleton";
import { Stamp } from "@/components/ui/stamp";
import { ApiError } from "@/lib/api/client";
import { type ArtifactStatus, useArtifact } from "@/lib/api/endpoints/artifacts";
import { ApprovalControls } from "./ApprovalControls";
import { TaskChecklistRender } from "./TaskChecklistRender";

interface ArtifactViewerProps {
  projectId: string;
  sessionId: string;
  name: string;
  status?: ArtifactStatus;
}

function formatSize(size: number | null): string | null {
  if (size === null) return null;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatMtime(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function ArtifactViewer({ projectId, sessionId, name, status }: ArtifactViewerProps) {
  // While `status` is still loading we don't know whether the artifact exists,
  // so refuse to fire the detail fetch until the list query resolves. Default
  // to `false` here instead of `true` — the brief "status-unknown" window is
  // rendered as a skeleton, not a premature network call.
  const statusLoading = status === undefined;
  const present = status?.present ?? false;
  const {
    data: artifact,
    isLoading,
    error,
  } = useArtifact(projectId, sessionId, name, !statusLoading && present);

  if (statusLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!present) {
    const expectedPath = status?.spec.file
      ? `sessions/${sessionId}/${status.spec.file}`
      : `sessions/${sessionId}/<file>`;
    return (
      <div
        className="rounded-md border border-dashed p-6 text-sm text-muted-foreground"
        data-testid="artifact-missing"
      >
        <p className="font-semibold text-foreground">Not yet produced.</p>
        <p className="mt-1">
          Expected at <code className="font-mono">{expectedPath}</code>.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return <p className="text-sm text-muted-foreground">Artifact file missing on disk.</p>;
    }
    return (
      <p className="text-sm text-red-500" role="alert">
        Failed to load artifact: {error instanceof Error ? error.message : "unknown"}
      </p>
    );
  }

  if (!artifact) return null;

  const isGated = status?.spec.approval_gate ?? false;
  const isTaskChecklist = name === "task-checklist";
  const size = status ? formatSize(status.size_bytes) : null;
  const mtime = status ? formatMtime(status.last_modified) : formatMtime(artifact.mtime);

  return (
    <article className="space-y-4" data-testid="artifact-viewer">
      <header className="flex flex-wrap items-center gap-2 text-sm">
        <h3 className="font-semibold text-foreground">{name}</h3>
        {status?.spec.produced_at ? <Stamp tone="default">{status.spec.produced_at}</Stamp> : null}
        {status?.spec.required ? <Stamp tone="info">required</Stamp> : null}
        <span className="ml-auto text-xs text-muted-foreground">
          {size ? <span>{size}</span> : null}
          {size && mtime ? <span> · </span> : null}
          {mtime ? <span>{mtime}</span> : null}
        </span>
      </header>

      {isTaskChecklist ? <TaskChecklistRender body={artifact.body} /> : null}

      <div className="min-h-0">
        <MarkdownBody content={artifact.body} projectId={projectId} />
      </div>

      {isGated ? (
        <ApprovalControls projectId={projectId} sessionId={sessionId} name={name} status={status} />
      ) : null}
    </article>
  );
}
