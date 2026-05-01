import { AlertTriangle } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { InboxPreviewDrawer } from "@/components/ui/inbox-preview-drawer";
import { sessionStageColor } from "@/components/ui/session-stage-row";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { LiveRail } from "./LiveRail";
import { TurnStream, type TurnStreamEntry } from "./TurnStream";
import { useLiveSession } from "./useLiveSession";

/**
 * Live Session Monitor — KUI-107 / S7.
 *
 * Single screen at `/p/:projectId/sessions/:sid/live`. Reads the
 * project-scoped WebSocket subscription that ProjectShell already
 * holds, so this page is data-only — no second WS open.
 *
 * Header colour is sourced from `sessionStageColor("executing")`
 * per the v0.8.x amendment so a future palette change ripples to
 * every surface (dashboard, board, live monitor) without per-surface
 * edits. When the session moves off-track mid-stream, the header
 * flips into alert chrome (border + bg tint + AlertTriangle +
 * status banner) and the auto-scroll-pause logic in TurnStream
 * stops chasing new content.
 */
export function LiveMonitor() {
  const { projectId, sid } = useParams<{ projectId: string; sid: string }>();
  if (!projectId || !sid) {
    return <NotFound projectId={projectId} />;
  }
  return <LiveMonitorInner projectId={projectId} sid={sid} />;
}

function LiveMonitorInner({ projectId, sid }: { projectId: string; sid: string }) {
  const live = useLiveSession(projectId, sid);
  const [openInboxId, setOpenInboxId] = useState<string | null>(null);

  // Build the turn stream — engagement entries from the session
  // (v2 runtime feature; empty in v1) plus JIT prompt fires from the
  // events stream interleaved by timestamp. The TurnStream owns
  // engagement-boundary divider rendering.
  const entries = useMemo<TurnStreamEntry[]>(() => {
    const session = live.session;
    if (!session) return [];

    type EngagementEntry = Extract<TurnStreamEntry, { kind: "engagement" }>;
    // Use direct property access — `session.engagements[]` is now the
    // typed `Engagement` interface from `endpoints/sessions.ts` (introduced
    // in S3 / KUI-103 Option C). The earlier `readString(e, "...")` helper
    // expected `Record<string, unknown>` and is no longer assignable here.
    const engagementEntries: EngagementEntry[] = (session.engagements ?? [])
      .map((e, idx): EngagementEntry | null => {
        if (!e.started_at) return null;
        return {
          kind: "engagement",
          id: e.engagement_id ?? `eng-${idx}`,
          timestamp: e.started_at,
          trigger: e.trigger ?? "spawn",
          endedAt: e.ended_at ?? null,
          outcome: e.outcome ?? null,
        };
      })
      .filter((x): x is EngagementEntry => x !== null);

    const fireEntries: TurnStreamEntry[] = live.jitPromptFires.map((fire) => ({
      kind: "jit_prompt_fire",
      id: fire.id,
      timestamp: fire.fired_at,
      jitPromptId: fire.jit_prompt_id ?? "(unnamed)",
    }));

    return [...engagementEntries, ...fireEntries].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );
  }, [live.session, live.jitPromptFires]);

  if (live.isLoading) {
    return <LoadingState />;
  }
  if (live.error) {
    if (live.error instanceof ApiError && live.error.status === 404) {
      return <NotFound projectId={projectId} />;
    }
    return (
      <div className="p-8 font-mono text-[12px] text-(--color-rule)" role="alert">
        Failed to load session.
      </div>
    );
  }
  if (!live.session) {
    return <NotFound projectId={projectId} />;
  }

  const session = live.session;
  const isOffTrack = live.isOffTrack;
  const liveColour = sessionStageColor("executing");

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header
        className={cn(
          "flex items-center gap-3 border-(--color-edge) border-b px-6 py-3",
          isOffTrack && "border-(--color-rule)/50 bg-(--color-rule)/10",
        )}
      >
        <h1 className="font-sans font-semibold text-[18px] text-(--color-ink) tracking-[-0.01em]">
          {session.name}
        </h1>
        <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
          {session.id} · {session.agent}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {isOffTrack ? (
            <OffTrackBanner status={session.status} />
          ) : (
            <LiveBadge colour={liveColour} />
          )}
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        <main className="flex flex-1 min-h-0 flex-col">
          <TurnStream entries={entries} isOffTrack={isOffTrack} />
        </main>
        <LiveRail
          projectId={projectId}
          sessionId={sid}
          status={session.status}
          costUsd={session.cost_usd}
          agentState={session.current_state}
          jitPromptFires={live.jitPromptFires}
          costApprovalEntry={live.costApprovalEntry}
          onCostApprovalClick={(id) => setOpenInboxId(id)}
        />
      </div>

      <InboxPreviewDrawer
        projectId={projectId}
        entryId={openInboxId}
        onClose={() => setOpenInboxId(null)}
      />
    </div>
  );
}

function LiveBadge({ colour }: { colour: string }) {
  return (
    <span
      data-testid="live-badge"
      className="inline-flex items-center gap-1.5 rounded-(--radius-stamp) border px-2 py-0.5 font-mono font-semibold text-[10px] uppercase tracking-[0.18em]"
      style={{ color: colour, borderColor: colour }}
    >
      <span
        className="inline-block h-1.5 w-1.5 animate-pulse rounded-full"
        aria-hidden
        style={{ background: colour }}
      />
      LIVE
    </span>
  );
}

function OffTrackBanner({ status }: { status: string }) {
  return (
    <div
      data-testid="off-track-banner"
      className="inline-flex items-center gap-2 rounded-(--radius-stamp) border border-(--color-rule) bg-(--color-rule)/10 px-2.5 py-1"
    >
      <AlertTriangle className="h-3.5 w-3.5 text-(--color-rule)" aria-hidden strokeWidth={2.4} />
      <span className="font-mono font-semibold text-[10px] text-(--color-rule) uppercase tracking-[0.18em]">
        OFF-TRACK · {status}
      </span>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-4 p-8">
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function NotFound({ projectId }: { projectId?: string }) {
  const sessionsHref = projectId ? `/p/${projectId}/sessions` : "/";
  return (
    <div className="p-8">
      <h1 className="font-sans font-semibold text-[20px] text-(--color-ink)">Session not found</h1>
      <Link to={sessionsHref} className="mt-4 inline-block text-sm underline">
        ← Back to sessions
      </Link>
    </div>
  );
}
