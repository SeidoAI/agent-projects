import { useDraggable } from "@dnd-kit/core";
import { Inbox } from "lucide-react";
import type { MouseEvent } from "react";

import { Stamp, type StampTone } from "@/components/ui/stamp";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import { cn } from "@/lib/utils";

/**
 * Issue card for the v0.8 Board's IssuesView column.
 *
 * Sibling of `BoardSessionCard`: shares the cross-link badge / stage
 * stripe / preview-drawer click affordance. Differs in body density
 * — issues surface owner + priority instead of agent + status.
 *
 * The existing `features/issues/IssueCard.tsx` stays for the issue
 * graph / search lists; this is the board-only render with the
 * cream/ink palette.
 */
export interface BoardIssueCardProps {
  issue: IssueSummary;
  blockedInboxCount?: number;
  onClick?: () => void;
  onCrossLinkClick?: () => void;
}

const PRIORITY_TONE: Record<string, StampTone> = {
  critical: "rule",
  high: "tripwire",
  medium: "default",
  low: "default",
};

export function BoardIssueCard({
  issue,
  blockedInboxCount = 0,
  onClick,
  onCrossLinkClick,
}: BoardIssueCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: issue.id,
    data: { type: "issue", status: issue.status },
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;
  const handleCrossLink = (e: MouseEvent) => {
    e.stopPropagation();
    onCrossLinkClick?.();
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      data-testid={`board-issue-card-${issue.id}`}
      className={cn(
        "relative flex flex-col gap-2 rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) px-3 py-2 text-(--color-ink) transition-shadow",
        "hover:border-(--color-ink-3) hover:shadow-sm",
        issue.is_epic && "border-2 border-dashed",
        isDragging && "opacity-50 shadow-md",
      )}
      {...attributes}
      {...listeners}
    >
      <header className="flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={onClick}
          className="flex min-w-0 flex-1 flex-col items-start gap-1 text-left"
        >
          <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
            {issue.id}
          </span>
          <span
            className={cn(
              "line-clamp-2 font-sans font-medium text-[13px] leading-tight",
              issue.is_epic && "font-semibold",
            )}
          >
            {issue.title}
          </span>
        </button>
        <div className="flex shrink-0 items-center gap-1.5">
          {issue.is_blocked ? (
            <span
              role="img"
              aria-label="blocked"
              title="blocked by upstream issue"
              className="inline-block h-2 w-2 rounded-full bg-(--color-rule)"
            />
          ) : null}
          <Stamp tone={PRIORITY_TONE[issue.priority] ?? "default"} variant="status">
            {issue.priority}
          </Stamp>
        </div>
      </header>
      <footer className="flex items-center justify-between gap-2 font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
        <span className="flex items-center gap-1.5">
          <span className="capitalize">{issue.executor}</span>
          {issue.agent ? (
            <>
              <span aria-hidden>·</span>
              <span>{issue.agent}</span>
            </>
          ) : null}
        </span>
        {blockedInboxCount > 0 ? (
          <button
            type="button"
            onClick={handleCrossLink}
            aria-label={`${blockedInboxCount} open blocked inbox entries`}
            className="inline-flex items-center gap-1 rounded-(--radius-stamp) border border-(--color-rule) bg-(--color-rule)/10 px-1.5 py-0.5 text-(--color-rule) tracking-[0.06em] hover:bg-(--color-rule)/20"
          >
            <Inbox className="h-3 w-3" aria-hidden />
            inbox{blockedInboxCount > 1 ? `·${blockedInboxCount}` : ""}
          </button>
        ) : null}
      </footer>
    </div>
  );
}
