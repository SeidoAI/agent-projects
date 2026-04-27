import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { AlertTriangle } from "lucide-react";
import { useMemo } from "react";
import { toast } from "sonner";

import {
  OFF_TRACK_STAGE_ID,
  SESSION_STAGES,
  sessionStageId,
} from "@/components/ui/session-stage-row";
import { Stamp } from "@/components/ui/stamp";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { cn } from "@/lib/utils";
import type { BlockedInboxIndex } from "./hooks/useBlockedInbox";
import { BoardSessionCard } from "./SessionCard";

/** The 6 in-flow stages that render as primary columns, in order.
 *  Off-track is a special-cased 8th column with alert chrome.
 *
 *  We deliberately import the canonical SESSION_STAGES rather than
 *  redefine the order — `[[session-stage-mapping]]` is the single
 *  source of truth, and the dashboard's stage row is the visual
 *  anchor users carry into this screen. */
const IN_FLOW_STAGES = SESSION_STAGES.filter((s) => s.id !== OFF_TRACK_STAGE_ID);
const OFF_TRACK_STAGE = SESSION_STAGES.find((s) => s.id === OFF_TRACK_STAGE_ID);
if (!OFF_TRACK_STAGE) throw new Error("session-stage-row.tsx is missing the off_track stage");

export interface SessionsViewProps {
  sessions: SessionSummary[];
  blockedInbox: BlockedInboxIndex;
  /** Per-stage filter — null means "show all in-flow stages". The
   *  off-track column is always rendered when off-track sessions
   *  exist, regardless of this filter. */
  activeStages: Set<string> | null;
  onCardClick: (session: SessionSummary) => void;
  onCrossLinkClick: (session: SessionSummary) => void;
}

interface ColumnBucket {
  stageId: string;
  label: string;
  color: string;
  sessions: SessionSummary[];
  isOffTrack: boolean;
}

function bucketSessions(sessions: SessionSummary[]): Map<string, SessionSummary[]> {
  const out = new Map<string, SessionSummary[]>();
  for (const s of sessions) {
    const stage = sessionStageId(s.status);
    if (!stage) continue;
    const arr = out.get(stage) ?? [];
    arr.push(s);
    out.set(stage, arr);
  }
  return out;
}

export function SessionsView({
  sessions,
  blockedInbox,
  activeStages,
  onCardClick,
  onCrossLinkClick,
}: SessionsViewProps) {
  const buckets = useMemo<ColumnBucket[]>(() => {
    const byStage = bucketSessions(sessions);
    const cols: ColumnBucket[] = IN_FLOW_STAGES.map((s) => ({
      stageId: s.id,
      label: s.label,
      color: s.color,
      sessions: byStage.get(s.id) ?? [],
      isOffTrack: false,
    }));
    const offTrack = byStage.get(OFF_TRACK_STAGE_ID) ?? [];
    if (offTrack.length > 0 && OFF_TRACK_STAGE) {
      cols.push({
        stageId: OFF_TRACK_STAGE.id,
        label: OFF_TRACK_STAGE.label,
        color: OFF_TRACK_STAGE.color,
        sessions: offTrack,
        isOffTrack: true,
      });
    }
    return cols;
  }, [sessions]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const fromStage = sessionStageId(String(active.data.current?.status ?? ""));
    const toStage = String(over.id);
    if (fromStage === toStage) return;
    // No backend endpoint exists for session status mutation
    // (see decisions.md D1). The UI snaps the card back and tells
    // the user where to perform the transition for real.
    toast.info("Session transitions go through the CLI", {
      description: `Run \`tripwire session transition ${active.id} ${toStage}\` (UI persistence is a fast-follow).`,
    });
  };

  return (
    <DndContext sensors={sensors} onDragEnd={onDragEnd}>
      <div className="flex h-full gap-2.5 overflow-x-auto px-1 py-2">
        {buckets.map((col) => {
          const visible = col.isOffTrack ? true : activeStages === null || activeStages.has(col.stageId);
          if (!visible) return null;
          return (
            <SessionColumn
              key={col.stageId}
              column={col}
              blockedInbox={blockedInbox}
              onCardClick={onCardClick}
              onCrossLinkClick={onCrossLinkClick}
            />
          );
        })}
      </div>
    </DndContext>
  );
}

function SessionColumn({
  column,
  blockedInbox,
  onCardClick,
  onCrossLinkClick,
}: {
  column: ColumnBucket;
  blockedInbox: BlockedInboxIndex;
  onCardClick: (s: SessionSummary) => void;
  onCrossLinkClick: (s: SessionSummary) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: column.stageId });
  return (
    <section
      aria-label={`${column.label} column`}
      className={cn(
        "flex h-full w-[260px] shrink-0 flex-col rounded-(--radius-card) border bg-(--color-paper-2) transition-colors",
        column.isOffTrack
          ? "border-(--color-rule) bg-(--color-rule)/8 ring-1 ring-(--color-rule)/40"
          : "border-(--color-edge)",
        isOver && !column.isOffTrack && "border-(--color-ink-3) bg-(--color-paper-3)/40",
      )}
    >
      <header className="flex items-center justify-between border-(--color-edge) border-b px-3 py-2">
        <div className="flex items-center gap-2">
          {column.isOffTrack ? (
            <AlertTriangle className="h-3.5 w-3.5 text-(--color-rule)" aria-hidden />
          ) : (
            <span
              aria-hidden
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: column.color }}
            />
          )}
          <span
            className={cn(
              "font-mono text-[11px] uppercase tracking-[0.06em]",
              column.isOffTrack ? "text-(--color-rule) font-semibold" : "text-(--color-ink)",
            )}
          >
            {column.label}
          </span>
        </div>
        <Stamp tone={column.isOffTrack ? "rule" : "default"} variant="numeric">
          {column.sessions.length}
        </Stamp>
      </header>
      <div
        ref={setNodeRef}
        data-testid={`board-session-column-${column.stageId}`}
        className="flex min-h-[8rem] flex-1 flex-col gap-2 overflow-y-auto px-2 py-2"
      >
        {column.sessions.length === 0 ? (
          <p className="px-1 py-4 text-center font-serif text-[12px] text-(--color-ink-3) italic">
            (empty)
          </p>
        ) : (
          column.sessions.map((s) => (
            <BoardSessionCard
              key={s.id}
              session={s}
              blockedInboxCount={blockedInbox.bySession.get(s.id)?.length ?? 0}
              onClick={() => onCardClick(s)}
              onCrossLinkClick={() => onCrossLinkClick(s)}
            />
          ))
        )}
      </div>
    </section>
  );
}
