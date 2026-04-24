import { useDraggable } from "@dnd-kit/core";
import { Link2 } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import { cn } from "@/lib/utils";

interface IssueCardProps {
  issue: IssueSummary;
  refCount?: number;
}

export function IssueCard({ issue, refCount }: IssueCardProps) {
  const { projectId } = useParams();
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: issue.id,
    data: { type: "issue", status: issue.status },
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  return (
    <div
      ref={setNodeRef}
      style={style}
      data-testid={`issue-card-${issue.id}`}
      className={cn(
        "rounded-md border bg-card p-3 text-card-foreground shadow-sm transition-shadow",
        issue.is_epic && "border-2 border-dashed",
        isDragging && "opacity-50 shadow-md",
      )}
      {...attributes}
      {...listeners}
    >
      <div className="flex items-start justify-between gap-2">
        {/* No stopPropagation here — dnd-kit's PointerSensor listens on
            the draggable root (this card) and a child-level stop would
            swallow `pointerdown` before the sensor ever sees it, which
            silently breaks drag-from-link-area. The `distance: 5`
            activation constraint on the sensor already keeps a plain
            click from registering as a drag. */}
        <Link
          to={`/p/${projectId}/issues/${issue.id}`}
          className={cn(
            "font-mono text-xs text-muted-foreground hover:text-foreground",
            issue.is_epic && "text-sm font-semibold",
          )}
        >
          {issue.id}
        </Link>
        <div className="flex items-center gap-1.5">
          {issue.is_blocked && (
            <span
              role="img"
              aria-label="Blocked"
              title="Blocked"
              className="inline-block h-2 w-2 rounded-full bg-destructive"
            />
          )}
          <PriorityBadge priority={issue.priority} />
        </div>
      </div>
      <div className={cn("mt-1 text-sm text-foreground", issue.is_epic && "font-semibold")}>
        {issue.title}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span className="capitalize">{issue.executor}</span>
        {issue.agent && (
          <>
            <span aria-hidden>·</span>
            <span>{issue.agent}</span>
          </>
        )}
        {typeof refCount === "number" && refCount > 0 && (
          <span
            role="img"
            className="ml-auto inline-flex items-center gap-1"
            aria-label={`${refCount} refs`}
          >
            <Link2 aria-hidden className="h-3 w-3" />
            {refCount}
          </span>
        )}
      </div>
    </div>
  );
}

const PRIORITY_STYLES: Record<string, string> = {
  critical: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
  high: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  medium: "border-muted-foreground/30 bg-muted text-muted-foreground",
  low: "border-muted-foreground/20 bg-muted/50 text-muted-foreground",
};

function PriorityBadge({ priority }: { priority: string }) {
  const style = PRIORITY_STYLES[priority] ?? PRIORITY_STYLES.medium;
  return (
    <Badge variant="outline" className={cn("text-[10px] capitalize", style)}>
      {priority}
    </Badge>
  );
}
