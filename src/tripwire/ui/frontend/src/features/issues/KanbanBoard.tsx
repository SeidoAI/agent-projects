import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { toast } from "sonner";

import { useProjectShell } from "@/app/ProjectShell";
import { Skeleton } from "@/components/ui/skeleton";
import type { ApiError } from "@/lib/api/client";
import type { EnumValue } from "@/lib/api/endpoints/enums";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import { cn } from "@/lib/utils";
import { useIssueStatusEnum, useIssues, useUpdateIssueStatus } from "./hooks/useIssues";
import { IssueCard } from "./IssueCard";

export function KanbanBoard() {
  const { projectId } = useProjectShell();
  const issues = useIssues(projectId);
  const statusEnum = useIssueStatusEnum(projectId);
  const update = useUpdateIssueStatus(projectId);

  // A 5px activation distance keeps clicks on the issue link from
  // starting a drag. Without it, every click becomes a micro-drag
  // and navigation stops working.
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const key = String(active.id);
    const nextStatus = String(over.id);
    const current = active.data.current?.status;
    if (current === nextStatus) return;

    update.mutate(
      { key, status: nextStatus },
      {
        onError: (err: ApiError) => {
          toast.error("Couldn't move issue", {
            description: err.message,
          });
        },
      },
    );
  };

  if (issues.isLoading || statusEnum.isLoading) {
    return <KanbanSkeleton />;
  }
  if (issues.isError || statusEnum.isError) {
    return (
      <div className="p-6 text-sm text-destructive">Couldn't load the board. Try refreshing.</div>
    );
  }

  const columns = statusEnum.data?.values ?? [];
  const allIssues = issues.data ?? [];

  return (
    <DndContext sensors={sensors} onDragEnd={onDragEnd}>
      <div className="flex h-full gap-3 overflow-x-auto p-4">
        {columns.map((col) => (
          <KanbanColumn
            key={col.value}
            column={col}
            issues={allIssues.filter((i) => i.status === col.value)}
          />
        ))}
      </div>
    </DndContext>
  );
}

function KanbanColumn({ column, issues }: { column: EnumValue; issues: IssueSummary[] }) {
  const { isOver, setNodeRef } = useDroppable({ id: column.value });
  return (
    <section
      aria-label={`${column.label} column`}
      className="flex h-full w-72 shrink-0 flex-col rounded-lg border bg-muted/30"
    >
      <header className="flex items-center justify-between border-b px-3 py-2">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: column.color ?? "currentColor" }}
          />
          <span className="text-sm font-semibold text-foreground">{column.label}</span>
        </div>
        <span className="text-xs text-muted-foreground">{issues.length}</span>
      </header>
      <div
        ref={setNodeRef}
        data-testid={`kanban-column-${column.value}`}
        className={cn(
          "flex min-h-[8rem] flex-1 flex-col gap-2 overflow-y-auto p-2 transition-colors",
          isOver && "bg-primary/5",
        )}
      >
        {issues.length === 0 ? (
          <p className="px-1 py-4 text-center text-xs text-muted-foreground">No issues</p>
        ) : (
          issues.map((issue) => <IssueCard key={issue.id} issue={issue} />)
        )}
      </div>
    </section>
  );
}

function KanbanSkeleton() {
  return (
    <div className="flex h-full gap-3 overflow-x-auto p-4">
      {[0, 1, 2, 3].map((n) => (
        <div key={n} className="flex w-72 shrink-0 flex-col gap-2 rounded-lg border p-3">
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ))}
    </div>
  );
}
