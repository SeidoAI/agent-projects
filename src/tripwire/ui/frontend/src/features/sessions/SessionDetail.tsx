import { AlertTriangle } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { InboxPreviewDrawer } from "@/components/ui/inbox-preview-drawer";
import { LifecycleWire } from "@/components/ui/lifecycle-wire";
import {
  OFF_TRACK_STAGE_ID,
  SESSION_STAGES,
  sessionStageColor,
  sessionStageId,
} from "@/components/ui/session-stage-row";
import { Skeleton } from "@/components/ui/skeleton";
import { Stamp } from "@/components/ui/stamp";
import { ApiError } from "@/lib/api/client";
import { useInbox } from "@/lib/api/endpoints/inbox";
import { type SessionDetail as SessionDetailType, useSession } from "@/lib/api/endpoints/sessions";
import { cn } from "@/lib/utils";

import { SessionEngagementList } from "./SessionEngagementList";
import { SessionEventFeed } from "./SessionEventFeed";
import { SessionPlanTab } from "./SessionPlanTab";
import { TaskProgressBar } from "./TaskProgressBar";

/** The 6 happy-path stages used by the mini-wire in the header.
 *  `off_track` is special-cased — when a session lands there, the
 *  header flips into alert chrome and the mini-wire is hidden. */
const IN_FLOW_STAGES = SESSION_STAGES.filter((s) => s.id !== OFF_TRACK_STAGE_ID).map((s) => ({
  id: s.id,
  label: s.label,
}));

export function SessionDetail() {
  const { projectId, sid } = useParams<{ projectId: string; sid: string }>();
  if (!projectId || !sid) return <NotFound projectId={projectId} />;
  // `key={sid}` remounts the subtree when the URL session id changes
  // so any local state (currently the inbox-preview-drawer selection)
  // resets cleanly.
  return <SessionDetailInner key={sid} projectId={projectId} sid={sid} />;
}

function SessionDetailInner({ projectId, sid }: { projectId: string; sid: string }) {
  const { data: session, isLoading, error } = useSession(projectId, sid);

  if (isLoading) {
    return (
      <div className="space-y-4 p-8">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return <NotFound projectId={projectId} />;
    }
    return (
      <div className="p-8 text-sm text-(--color-rule)" role="alert">
        Failed to load session.
      </div>
    );
  }

  if (!session) return <NotFound projectId={projectId} />;
  return <SessionDetailReady projectId={projectId} session={session} />;
}

function SessionDetailReady({
  projectId,
  session,
}: {
  projectId: string;
  session: SessionDetailType;
}) {
  const stageId = sessionStageId(session.status);
  const isOffTrack = stageId === OFF_TRACK_STAGE_ID;
  const stageColor = sessionStageColor(session.status);
  const currentIndex = useMemo(
    () => IN_FLOW_STAGES.findIndex((s) => s.id === stageId),
    [stageId],
  );

  // Inbox cross-link: surface unresolved entries that reference this
  // session id. We filter client-side rather than adding a dedicated
  // server endpoint — the inbox list is small (PM-authored only) and
  // already cached at the dashboard.
  const inbox = useInbox(projectId);
  const linkedInbox = useMemo(
    () =>
      (inbox.data ?? []).filter(
        (item) =>
          !item.resolved &&
          item.references.some((ref) => "session" in ref && ref.session === session.id),
      ),
    [inbox.data, session.id],
  );
  const blockedCount = linkedInbox.filter((i) => i.bucket === "blocked").length;
  const fyiCount = linkedInbox.length - blockedCount;
  const inboxChipLabel = blockedCount > 0
    ? `${blockedCount} blocked`
    : fyiCount > 0
      ? `${fyiCount} fyi`
      : null;

  const [previewInboxId, setPreviewInboxId] = useState<string | null>(null);

  return (
    <article className="flex flex-col gap-6 p-8">
      <header
        data-off-track={String(isOffTrack)}
        className={cn(
          "flex flex-col gap-3 rounded-(--radius-stamp) px-4 py-3",
          isOffTrack
            ? "border border-(--color-rule) bg-(--color-rule)/10 ring-1 ring-(--color-rule)/40"
            : "border border-(--color-edge) bg-(--color-paper)",
        )}
      >
        <div className="flex flex-wrap items-center gap-3">
          {isOffTrack ? (
            <AlertTriangle
              className="h-4 w-4 text-(--color-rule)"
              strokeWidth={2.4}
              aria-hidden
            />
          ) : null}
          <Stamp variant="identifier">{session.id}</Stamp>
          <h1 className="font-sans font-semibold text-[20px] text-(--color-ink) leading-tight tracking-[-0.01em]">
            {session.name || `Session ${session.id}`}
          </h1>
          <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.06em]">
            {session.agent}
          </span>
          {session.status ? (
            <span
              className="inline-flex items-center gap-1.5 rounded-(--radius-stamp) border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.06em]"
              style={{ borderColor: stageColor, color: stageColor }}
            >
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                aria-hidden
                style={{ background: stageColor }}
              />
              {session.status.replace(/_/g, " ")}
            </span>
          ) : null}
          {session.estimated_size ? (
            <Stamp tone="info" variant="status">
              size · {session.estimated_size}
            </Stamp>
          ) : null}
          {inboxChipLabel ? (
            <button
              type="button"
              onClick={() => setPreviewInboxId(linkedInbox[0]?.id ?? null)}
              aria-label={`inbox · ${inboxChipLabel} for this session`}
              className="ml-auto inline-flex items-center gap-1.5 rounded-(--radius-stamp) border border-(--color-rule) bg-(--color-rule)/10 px-2 py-0.5 font-mono text-[10px] text-(--color-rule) uppercase tracking-[0.06em] hover:bg-(--color-rule)/20"
            >
              inbox · {inboxChipLabel}
            </button>
          ) : null}
        </div>
        {session.blocked_by_sessions.length > 0 ? (
          <p
            className="font-mono text-[11px] text-(--color-rule) tracking-[0.06em]"
            data-field="blocked-by"
          >
            blocked by: {session.blocked_by_sessions.join(", ")}
          </p>
        ) : null}
        <div className="max-w-md">
          <TaskProgressBar progress={session.task_progress} />
        </div>
        {!isOffTrack && currentIndex >= 0 ? (
          <div className="-mx-2">
            <LifecycleWire stations={IN_FLOW_STAGES} currentIndex={currentIndex} height={64} />
          </div>
        ) : null}
      </header>

      <section>
        <h2 className="mb-2 font-mono text-[11px] text-(--color-ink-3) uppercase tracking-[0.18em]">
          Plan
        </h2>
        <SessionPlanTab planMd={session.plan_md} projectId={projectId} />
      </section>

      <section>
        <h2 className="mb-2 font-mono text-[11px] text-(--color-ink-3) uppercase tracking-[0.18em]">
          Engagements
        </h2>
        <SessionEngagementList engagements={session.engagements} />
      </section>

      <section>
        <h2 className="mb-2 font-mono text-[11px] text-(--color-ink-3) uppercase tracking-[0.18em]">
          Events
        </h2>
        <SessionEventFeed projectId={projectId} sessionId={session.id} />
      </section>

      <InboxPreviewDrawer
        projectId={projectId}
        entryId={previewInboxId}
        onClose={() => setPreviewInboxId(null)}
        prefetchedItem={
          previewInboxId
            ? (linkedInbox.find((item) => item.id === previewInboxId) ?? null)
            : null
        }
      />
    </article>
  );
}

function NotFound({ projectId }: { projectId?: string }) {
  const sessionsHref = projectId ? `/p/${projectId}/sessions` : "/projects";
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-(--color-ink)">Session not found</h1>
      <Link to={sessionsHref} className="mt-4 inline-block text-sm underline">
        ← Back to sessions
      </Link>
    </div>
  );
}
