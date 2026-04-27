import { useDraggable } from "@dnd-kit/core";
import { Inbox } from "lucide-react";
import type { MouseEvent } from "react";

import { sessionStageColor } from "@/components/ui/session-stage-row";
import { Stamp } from "@/components/ui/stamp";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { cn } from "@/lib/utils";

/**
 * Card rendered in the SessionsView columns of the v0.8 Board.
 *
 * The status pill stripe pulls from `sessionStageColor()` (the
 * canonical mapping in [[session-stage-row]]) so the colour matches
 * the dashboard's stage row. Re-engagement count and inbox cross-link
 * sit in the header next to the id.
 *
 * Per [[dec-shared-preview-drawer]] clicking the card body opens the
 * preview drawer (handled by the parent — the card just fires
 * `onClick`); clicking the inbox badge opens the same drawer scoped
 * to the inbox entry.
 */
export interface BoardSessionCardProps {
  session: SessionSummary;
  /** Count of open BLOCKED inbox entries that reference this session;
   *  any positive count surfaces the cross-link badge. */
  blockedInboxCount?: number;
  /** Click on the card body — typically opens the preview drawer. */
  onClick?: () => void;
  /** Click on the inbox cross-link chip — opens drawer to that
   *  inbox entry (parent decides which one if there are multiple). */
  onCrossLinkClick?: () => void;
}

export function BoardSessionCard({
  session,
  blockedInboxCount = 0,
  onClick,
  onCrossLinkClick,
}: BoardSessionCardProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: session.id,
    data: { type: "session", status: session.status },
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;
  const stageColor = sessionStageColor(session.status);
  const handleCrossLink = (e: MouseEvent) => {
    // Stop the click from bubbling into the card body — otherwise
    // the preview drawer would also open and clobber the cross-link
    // navigation the user actually intended.
    e.stopPropagation();
    onCrossLinkClick?.();
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      data-testid={`session-card-${session.id}`}
      className={cn(
        "group relative flex flex-col gap-2 rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) px-3 py-2 text-(--color-ink) transition-shadow",
        "hover:border-(--color-ink-3) hover:shadow-sm",
        isDragging && "opacity-50 shadow-md",
      )}
      {...attributes}
      {...listeners}
    >
      {/* Status colour stripe down the left edge — mirrors the
          dashboard stage card. */}
      <span
        aria-hidden
        className="absolute top-0 bottom-0 left-0 w-[3px] rounded-l-(--radius-card)"
        style={{ background: stageColor }}
      />
      <header className="flex items-start justify-between gap-2">
        <button
          type="button"
          onClick={onClick}
          className="flex min-w-0 flex-1 flex-col items-start gap-1 text-left"
        >
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
              {session.id}
            </span>
            {session.re_engagement_count > 0 ? (
              <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
                ↺ {session.re_engagement_count}
              </span>
            ) : null}
          </div>
          <div className="line-clamp-2 font-sans font-medium text-[13px] leading-tight">
            {session.name}
          </div>
        </button>
        {blockedInboxCount > 0 ? (
          <button
            type="button"
            onClick={handleCrossLink}
            aria-label={`${blockedInboxCount} open blocked inbox entries`}
            className="inline-flex shrink-0 items-center gap-1 rounded-(--radius-stamp) border border-(--color-rule) bg-(--color-rule)/10 px-1.5 py-0.5 font-mono text-[10px] text-(--color-rule) tracking-[0.06em] hover:bg-(--color-rule)/20"
          >
            <Inbox className="h-3 w-3" aria-hidden />
            inbox{blockedInboxCount > 1 ? `·${blockedInboxCount}` : ""}
          </button>
        ) : null}
      </header>
      <footer className="flex items-center justify-between gap-2 font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
        <span>{session.agent}</span>
        <Stamp tone="default" variant="status">
          {session.status}
        </Stamp>
      </footer>
    </div>
  );
}
