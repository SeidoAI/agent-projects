import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { toast } from "sonner";

import { Stamp } from "@/components/ui/stamp";
import type { ApiError } from "@/lib/api/client";
import type { EnumValue } from "@/lib/api/endpoints/enums";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import { useUpdateIssueStatus } from "@/features/issues/hooks/useIssues";
import { cn } from "@/lib/utils";
import type { BlockedInboxIndex } from "./hooks/useBlockedInbox";
import { BoardIssueCard } from "./IssueCard";

/** Issues swap of the v0.8 Board. Columns come from the project's
 *  `issue_status` enum (so adding a new status downstream auto-adds
 *  a column without code changes). Drag-across triggers the existing
 *  PATCH; the backend's `_validate_transition` rejects forbidden
 *  transitions, and we surface that failure as a snap-back + toast
 *  in the shape the AC asks for. */
export interface IssuesViewProps {
  projectId: string;
  issues: IssueSummary[];
  statusValues: EnumValue[];
  blockedInbox: BlockedInboxIndex;
  onCardClick: (issue: IssueSummary) => void;
  onCrossLinkClick: (issue: IssueSummary) => void;
}

export function IssuesView({
  projectId,
  issues,
  statusValues,
  blockedInbox,
  onCardClick,
  onCrossLinkClick,
}: IssuesViewProps) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const update = useUpdateIssueStatus(projectId);

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const fromStatus = String(active.data.current?.status ?? "");
    const toStatus = String(over.id);
    if (fromStatus === toStatus) return;
    update.mutate(
      { key: String(active.id), status: toStatus },
      {
        onError: (err: ApiError) => {
          // The backend's status-transition validator returns the
          // exact "Invalid transition X → Y" message; surface it
          // verbatim so the user sees which gate validator (per
          // [[validator-primitive]]) blocked the move. Snap-back
          // happens automatically because the optimistic update
          // rolls back on error.
          toast.error("Transition blocked", {
            description: err.message,
          });
        },
      },
    );
  };

  return (
    <DndContext sensors={sensors} onDragEnd={onDragEnd}>
      <div className="flex h-full gap-2.5 overflow-x-auto px-1 py-2">
        {statusValues.map((s) => (
          <IssueColumn
            key={s.value}
            status={s}
            issues={issues.filter((i) => i.status === s.value)}
            blockedInbox={blockedInbox}
            onCardClick={onCardClick}
            onCrossLinkClick={onCrossLinkClick}
          />
        ))}
      </div>
    </DndContext>
  );
}

function IssueColumn({
  status,
  issues,
  blockedInbox,
  onCardClick,
  onCrossLinkClick,
}: {
  status: EnumValue;
  issues: IssueSummary[];
  blockedInbox: BlockedInboxIndex;
  onCardClick: (i: IssueSummary) => void;
  onCrossLinkClick: (i: IssueSummary) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status.value });
  return (
    <section
      aria-label={`${status.label} column`}
      className={cn(
        "flex h-full w-[260px] shrink-0 flex-col rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) transition-colors",
        isOver && "border-(--color-ink-3) bg-(--color-paper-3)/40",
      )}
    >
      <header className="flex items-center justify-between border-(--color-edge) border-b px-3 py-2">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: status.color ?? "var(--color-ink-3)" }}
          />
          <span className="font-mono text-[11px] text-(--color-ink) uppercase tracking-[0.06em]">
            {status.label}
          </span>
        </div>
        <Stamp tone="default" variant="numeric">
          {issues.length}
        </Stamp>
      </header>
      <div
        ref={setNodeRef}
        data-testid={`board-issue-column-${status.value}`}
        className="flex min-h-[8rem] flex-1 flex-col gap-2 overflow-y-auto px-2 py-2"
      >
        {issues.length === 0 ? (
          <p className="px-1 py-4 text-center font-serif text-[12px] text-(--color-ink-3) italic">
            (empty)
          </p>
        ) : (
          issues.map((i) => (
            <BoardIssueCard
              key={i.id}
              issue={i}
              blockedInboxCount={blockedInbox.byIssue.get(i.id)?.length ?? 0}
              onClick={() => onCardClick(i)}
              onCrossLinkClick={() => onCrossLinkClick(i)}
            />
          ))
        )}
      </div>
    </section>
  );
}
