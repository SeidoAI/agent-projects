import { FileCode2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { NodeSource } from "@/lib/api/endpoints/nodes";
import { useProject } from "@/lib/api/endpoints/project";

interface NodeSourcePanelProps {
  source: NodeSource;
  projectId: string;
}

function lineFragment(lines: NodeSource["lines"]): string {
  if (!lines) return "";
  const [start, end] = lines;
  if (start === end) return `#L${start}`;
  return `#L${start}-L${end}`;
}

function openInEditorHref(source: NodeSource, localPath?: string | null): string | null {
  if (!localPath) return null;
  const base = localPath.replace(/\/$/, "");
  return `file://${base}/${source.path}${lineFragment(source.lines)}`;
}

function githubHref(source: NodeSource): string | null {
  if (!source.repo.includes("/")) return null;
  const branch = source.branch ?? "main";
  return `https://github.com/${source.repo}/blob/${branch}/${source.path}${lineFragment(source.lines)}`;
}

export function NodeSourcePanel({ source, projectId }: NodeSourcePanelProps) {
  const { data: project } = useProject(projectId);
  const repoEntry = project?.repos?.[source.repo];
  const localPath = repoEntry?.local ?? null;

  const href = openInEditorHref(source, localPath) ?? githubHref(source);
  const isLocal = Boolean(localPath);

  return (
    <section aria-labelledby="node-source-heading" className="rounded-md border p-4">
      <h2 id="node-source-heading" className="mb-2 text-sm font-semibold text-foreground">
        Source
      </h2>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted-foreground">repo</dt>
        <dd className="font-mono" data-field="repo">
          {source.repo}
        </dd>
        <dt className="text-muted-foreground">path</dt>
        <dd className="font-mono" data-field="path">
          {source.path}
        </dd>
        {source.lines ? (
          <>
            <dt className="text-muted-foreground">lines</dt>
            <dd className="font-mono" data-field="lines">
              {source.lines[0]}–{source.lines[1]}
            </dd>
          </>
        ) : null}
        {source.content_hash ? (
          <>
            <dt className="text-muted-foreground">hash</dt>
            <dd
              className="truncate font-mono text-xs text-muted-foreground"
              title={source.content_hash}
              data-field="hash"
            >
              {source.content_hash}
            </dd>
          </>
        ) : null}
        {source.branch ? (
          <>
            <dt className="text-muted-foreground">branch</dt>
            <dd className="font-mono" data-field="branch">
              {source.branch}
            </dd>
          </>
        ) : null}
      </dl>
      {href ? (
        <Button asChild variant="outline" size="sm" className="mt-3">
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={isLocal ? "Open source in editor" : "Open source on GitHub"}
          >
            <FileCode2 className="mr-1 h-3.5 w-3.5" />
            {isLocal ? "Open in editor" : "View on GitHub"}
          </a>
        </Button>
      ) : null}
    </section>
  );
}
