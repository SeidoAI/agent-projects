import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { AttentionQueue } from "@/components/ui/attention-queue";
import { CriticalPathSpine } from "@/components/ui/critical-path-spine";
import { InboxPreviewDrawer } from "@/components/ui/inbox-preview-drawer";
import { MarginNote } from "@/components/ui/margin-note";
import {
  SessionStageRow,
  sessionStageColor,
  sessionStageId,
  UNASSIGNED_STAGE_ID,
} from "@/components/ui/session-stage-row";
import { Stamp } from "@/components/ui/stamp";
import { useInbox, useResolveInbox } from "@/lib/api/endpoints/inbox";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import { type ProjectDetail, useProject } from "@/lib/api/endpoints/project";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { computeCriticalPath } from "./hooks/useCriticalPath";
import { bucketByStage, useProjectStats } from "./hooks/useProjectStats";

/**
 * Project Dashboard — first thing the PM sees (per spec §3.2).
 *
 * Re-framed around the question: "Where does my attention deliver
 * most leverage?" Top row of session-stage filter cards, then a
 * critical-path spine (phase B), then a two-column body
 * (attention queue ‖ live sessions, phase C). See
 * /Users/maia/.claude/plans/wobbly-juggling-flute.md for the full
 * design rationale.
 */
const DEFAULT_SELECTED_STAGES: ReadonlyArray<string> = ["executing", "in_review"];

export function ProjectDashboard() {
  const { projectId } = useProjectShell();
  const project = useProject(projectId);
  const stats = useProjectStats(projectId);

  // Selected stage filter — drives the right column. Default is the
  // "what's live" pair. Plain click replaces selection (or clears
  // when clicking the only-selected card); cmd/ctrl+click is
  // additive.
  const [selectedStages, setSelectedStages] = useState<Set<string>>(
    () => new Set(DEFAULT_SELECTED_STAGES),
  );
  // Selected inbox entry id for the preview drawer. null = closed.
  const [selectedInboxId, setSelectedInboxId] = useState<string | null>(null);

  // Selected blocker — when set (via a critical-path chip click),
  // takes precedence over the stage filter. Right column shows the
  // blocker session at the top + every session it directly blocks.
  // Click the same chip again, or the × on the column subtitle, to
  // clear and revert to the stage filter.
  const [selectedBlocker, setSelectedBlocker] = useState<string | null>(null);
  const handleSelectBlocker = (id: string) => {
    setSelectedBlocker((prev) => (prev === id ? null : id));
  };

  const handleStageClick = (stageId: string, additive: boolean) => {
    setSelectedStages((prev) => {
      const next = new Set(prev);
      if (additive) {
        if (next.has(stageId)) next.delete(stageId);
        else next.add(stageId);
      } else {
        if (next.has(stageId) && next.size === 1) {
          next.clear();
        } else {
          next.clear();
          next.add(stageId);
        }
      }
      return next;
    });
  };

  const issues = stats.issues;
  const realInbox = useInbox(projectId);
  const resolveInbox = useResolveInbox(projectId);
  const inboxItems = realInbox.data ?? [];
  const handleResolveInbox = (id: string) => resolveInbox.mutate({ id });
  const sessions = sortSessionsByStageFlow(stats.sessions);
  const criticalPath = computeCriticalPath(sessions);
  // Buckets are computed from the (possibly demo-augmented) session
  // list — counts and the right-column filter share one source of
  // truth, so the off-track card badge and the visible off-track
  // session rows always agree.
  const buckets = bucketByStage(sessions, issues);

  // Right column display logic. Blocker filter takes precedence
  // over stage filter when set: the column collapses to the
  // blocker + its directly-blocked sessions only.
  const blockerView = selectedBlocker ? computeBlockerView(sessions, selectedBlocker) : null;
  const filteredSessions = filterSessionsByStages(sessions, selectedStages);
  const showUnassigned = selectedStages.has(UNASSIGNED_STAGE_ID);
  const unassignedIssues = showUnassigned ? unassignedIssuesOf(sessions, issues) : [];

  const heading = project.data?.name ?? projectId;
  const description = project.data?.description?.trim() || null;

  return (
    <div className="px-7 pt-6 pb-8 text-(--color-ink)">
      <header className="flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex items-center gap-2">
            <Stamp variant="identifier">{projectId}</Stamp>
            <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
              chapter 01 · overview
            </span>
          </div>
          <h1 className="m-0 font-sans font-semibold text-[44px] leading-none tracking-[-0.025em] text-(--color-ink)">
            {heading}.
          </h1>
          {description ? (
            <p className="mt-3 max-w-[900px] whitespace-pre-line font-sans text-[15px] text-(--color-ink-2) leading-relaxed">
              {description}
            </p>
          ) : null}
        </div>
        <ProjectMeta project={project.data ?? null} />
      </header>

      <section className="mt-6 rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) px-6 pt-5 pb-5">
        <div className="mb-3 flex items-baseline justify-between">
          <SectionTitle sub={`${stats.totalIssues} issues across the project`}>
            Session stages
          </SectionTitle>
          <div className="flex items-center gap-3">
            <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
              cmd/ctrl+click to multi-select
            </span>
            {selectedStages.size > 0 ? (
              <button
                type="button"
                onClick={() => setSelectedStages(new Set())}
                className="inline-flex items-center gap-1.5 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-2.5 py-1 font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em] transition-colors hover:border-(--color-ink-3) hover:text-(--color-ink)"
              >
                clear filter ×
              </button>
            ) : null}
          </div>
        </div>
        <SessionStageRow
          buckets={buckets}
          selected={selectedStages}
          onStageClick={handleStageClick}
        />
      </section>

      <CriticalPathSpine
        result={criticalPath}
        selectedBlocker={selectedBlocker}
        onSelectBlocker={handleSelectBlocker}
        className="mt-4"
      />

      <InboxPreviewDrawer
        projectId={projectId}
        entryId={selectedInboxId}
        onClose={() => setSelectedInboxId(null)}
      />

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
        <AttentionQueue
          items={inboxItems}
          onResolve={handleResolveInbox}
          onSelectItem={setSelectedInboxId}
        />
        <LiveNowColumn
          sessions={filteredSessions}
          unassignedIssues={unassignedIssues}
          blockerView={blockerView}
          onClearBlocker={() => setSelectedBlocker(null)}
          projectId={projectId}
          selectedStages={selectedStages}
        />
      </div>
    </div>
  );
}

/** Lifecycle stage order for the right-column session list. Off-
 *  track sessions float to the top (most attention-worthy);
 *  everything else follows the natural flow. Sessions whose
 *  status maps to no stage (e.g. genuinely unknown) are sorted
 *  to the very end. */
const STAGE_SORT_ORDER: Record<string, number> = {
  off_track: 0,
  planned: 1,
  queued: 2,
  executing: 3,
  in_review: 4,
  verified: 5,
  completed: 6,
};

function sortSessionsByStageFlow(sessions: SessionSummary[]): SessionSummary[] {
  const indexFor = (s: SessionSummary): number => {
    const stageId = sessionStageId(s.status);
    if (!stageId) return Number.POSITIVE_INFINITY;
    return STAGE_SORT_ORDER[stageId] ?? Number.POSITIVE_INFINITY;
  };
  return [...sessions].sort((a, b) => indexFor(a) - indexFor(b));
}

/** Filter the full session list by the active stage selection.
 *
 *  Off-track sessions are ALWAYS surfaced at the top regardless of
 *  the stage filter — the user explicitly called them out as the
 *  most attention-worthy state, so hiding them behind a filter
 *  click would defeat the point. The stage filter governs the
 *  remaining (in-flow) sessions only.
 *
 *  - Empty selection: off-track at top + every other session (the
 *    "show everything that exists" view).
 *  - Non-empty selection: off-track at top + sessions whose stage
 *    id is in the set. The `unassigned` selection alone shows no
 *    sessions besides off-track (issues are handled separately
 *    by the right column).
 */
function filterSessionsByStages(
  sessions: SessionSummary[],
  selected: Set<string>,
): SessionSummary[] {
  const offTrack = sessions.filter((s) => sessionStageId(s.status) === "off_track");
  const inFilter =
    selected.size === 0
      ? sessions.filter((s) => sessionStageId(s.status) !== "off_track")
      : sessions.filter((s) => {
          const stageId = sessionStageId(s.status);
          return stageId !== null && stageId !== "off_track" && selected.has(stageId);
        });
  return [...offTrack, ...inFilter];
}

/** Issues not attached to any session AND not at a terminal status —
 *  backlog/sprawl signal. v0.9.4: terminal-status issues (completed,
 *  abandoned, plus the legacy aliases done/canceled for any pre-v0.9.4
 *  data still on disk) drop out of the unassigned bucket; they belong
 *  in their session's "completed" view, not in the agent's lap.
 *
 *  Pre-v0.9.4 the bucket was `!assigned`, which dragged every closed
 *  issue here whenever its session terminated. The user-visible symptom
 *  was every `done` issue showing under "unassigned" once Wave-N
 *  closeout flipped the issue to terminal but didn't keep the session
 *  membership tight. */
const TERMINAL_ISSUE_STATUSES = new Set([
  "completed",
  "abandoned",
  // Legacy aliases — accept on read until v1.0.
  "done",
  "canceled",
]);

function unassignedIssuesOf(sessions: SessionSummary[], issues: IssueSummary[]): IssueSummary[] {
  const assigned = new Set<string>();
  for (const s of sessions) for (const id of s.issues) assigned.add(id);
  return issues.filter(
    (i) => !assigned.has(i.id) && !TERMINAL_ISSUE_STATUSES.has(String(i.status)),
  );
}

/** Compute the right-column view when a blocker is selected via
 *  the critical-path spine. Returns the blocker session itself
 *  plus every session that directly depends on it (i.e. has
 *  `blockerId` in its `blocked_by_sessions`). Both halves may be
 *  empty if the demo mock injects ids that don't exist in the
 *  real session list — that's the right thing: the column simply
 *  shows "no sessions match." */
export interface BlockerView {
  blockerId: string;
  blocker: SessionSummary | null;
  blocked: SessionSummary[];
}

function computeBlockerView(sessions: SessionSummary[], blockerId: string): BlockerView {
  const blocker = sessions.find((s) => s.id === blockerId) ?? null;
  const blocked = sessions.filter((s) => s.blocked_by_sessions.includes(blockerId));
  return { blockerId, blocker, blocked };
}

/** Right-side meta cluster in the dashboard header — repos + phase.
 *
 *  The project-tracking repo (the one whose checkout IS the project
 *  itself) gets singled out with a "project repo · ..." label and
 *  rendered first. Code repos get "repo · ..." Detection: repo whose
 *  `local` path matches the project's `dir`. Falls back to the
 *  conventional `<org>/<project.name>` match if `dir` isn't set
 *  (older project.yaml without it).
 *
 *  Repo names are hyperlinks to their github URLs (uses the project
 *  yaml's `github` field if set, else falls back to
 *  `https://github.com/<repo-name>`). */
function ProjectMeta({ project }: { project: ProjectDetail | null }) {
  if (!project) return null;
  const repos = Object.entries(project.repos ?? {});
  const isPtRepo = (name: string, info: { local?: string | null } | undefined): boolean => {
    if (info?.local && project.dir && info.local === project.dir) return true;
    // Fallback for projects without `dir` on the API response: the
    // PT repo by convention matches `<something>/<project.name>`.
    return name.endsWith(`/${project.name}`);
  };
  const sorted = [...repos].sort(([nameA, infoA], [nameB, infoB]) => {
    const a = isPtRepo(nameA, infoA) ? 0 : 1;
    const b = isPtRepo(nameB, infoB) ? 0 : 1;
    return a - b;
  });
  return (
    <div className="flex flex-col items-end gap-1.5 font-mono text-[11px] text-(--color-ink-3)">
      {sorted.map(([name, info]) => {
        const href = info?.github ?? `https://github.com/${name}`;
        const label = isPtRepo(name, info) ? "project repo" : "repo";
        return (
          <div key={name}>
            {label} ·{" "}
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="text-(--color-ink) underline decoration-(--color-edge) decoration-1 underline-offset-2 hover:decoration-(--color-rule)"
            >
              {name}
            </a>
          </div>
        );
      })}
      {project.phase ? (
        <Stamp tone="rule" className="mt-1.5">
          phase · {project.phase}
        </Stamp>
      ) : null}
    </div>
  );
}

function SectionTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div>
      <h2 className="m-0 font-sans font-semibold text-[22px] leading-tight tracking-[-0.02em] text-(--color-ink)">
        {children}
      </h2>
      {sub ? (
        <MarginNote className="mt-1 text-[14px] text-(--color-ink-3)">{sub}</MarginNote>
      ) : null}
    </div>
  );
}

function LiveNowColumn({
  sessions,
  unassignedIssues,
  blockerView,
  onClearBlocker,
  projectId,
  selectedStages,
}: {
  sessions: SessionSummary[];
  unassignedIssues: IssueSummary[];
  blockerView: BlockerView | null;
  onClearBlocker: () => void;
  projectId: string;
  selectedStages: Set<string>;
}) {
  // Compute view-specific header + body data inside one stable
  // <section> so React doesn't unmount/remount on filter switch
  // (which was visibly resetting the page scroll).
  let subtitle: string | undefined;
  let countDisplay = "";
  let body: React.ReactNode;
  let trailingControl: React.ReactNode = null;

  if (blockerView) {
    const { blocker, blocked, blockerId } = blockerView;
    subtitle = `blocker · ${blockerId}`;
    const totalCount = (blocker ? 1 : 0) + blocked.length;
    countDisplay =
      blocked.length === 0
        ? blocker
          ? "1 blocker · 0 blocked"
          : "no matching sessions"
        : `1 blocker · ${blocked.length} blocked`;
    trailingControl = (
      <button
        type="button"
        onClick={onClearBlocker}
        className="font-mono text-[10px] text-(--color-rule) uppercase tracking-[0.18em] hover:text-(--color-ink)"
      >
        clear ×
      </button>
    );
    body =
      totalCount === 0 ? (
        <Empty>blocker not in current session list</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {blocker ? (
            <li>
              <SessionRow session={blocker} projectId={projectId} blockerLabel="blocker" />
            </li>
          ) : null}
          {blocked.map((s) => (
            <li key={s.id}>
              <SessionRow session={s} projectId={projectId} />
            </li>
          ))}
        </ul>
      );
  } else {
    const filterLabels = [...selectedStages].map((s) => s.replace(/_/g, " "));
    subtitle = filterLabels.length > 0 ? `filtered to ${filterLabels.join(" + ")}` : undefined;
    const totalCount = sessions.length + unassignedIssues.length;
    const noun = sessions.length > 0 ? "session" : "issue";
    countDisplay = totalCount === 0 ? "" : `${totalCount} ${noun}${totalCount === 1 ? "" : "s"}`;
    body =
      totalCount === 0 ? (
        <Empty>no sessions</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {unassignedIssues.map((i) => (
            <li key={`iss-${i.id}`}>
              <UnassignedIssueRow issue={i} projectId={projectId} />
            </li>
          ))}
          {sessions.map((s) => (
            <li key={s.id}>
              <SessionRow session={s} projectId={projectId} />
            </li>
          ))}
        </ul>
      );
  }

  return (
    <section className="rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <SectionTitle sub={subtitle}>Sessions</SectionTitle>
        <div className="flex shrink-0 items-baseline gap-3">
          <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
            {countDisplay}
          </span>
          {trailingControl}
        </div>
      </div>
      {body}
    </section>
  );
}

function SessionRow({
  session,
  projectId,
  blockerLabel,
}: {
  session: SessionSummary;
  projectId: string;
  blockerLabel?: string;
}) {
  const state = session.status ?? session.current_state ?? undefined;
  const stageColor = sessionStageColor(state);
  // Off-track sessions get the same alert chrome as the off-
  // track stage card: red border, rule-tinted background,
  // warning icon next to the id. Takes precedence over the
  // blocker-label highlight (off-track is the more urgent
  // signal of the two).
  const isOffTrack = sessionStageId(state) === "off_track";
  const className = isOffTrack
    ? "block rounded-(--radius-stamp) border border-(--color-rule) bg-(--color-rule)/10 px-3 py-2 ring-1 ring-(--color-rule)/40 transition-colors hover:border-(--color-rule)"
    : blockerLabel
      ? "block rounded-(--radius-stamp) border border-(--color-rule) bg-(--color-rule)/5 px-3 py-2 transition-colors hover:border-(--color-rule)"
      : "block rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2 transition-colors hover:border-(--color-ink-3)";
  return (
    <Link
      to={`/p/${projectId}/sessions/${session.id}`}
      aria-label={`Session ${session.id}`}
      className={className}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {isOffTrack ? (
            <AlertTriangle
              className="h-3.5 w-3.5 text-(--color-rule)"
              strokeWidth={2.4}
              aria-hidden
            />
          ) : null}
          <Stamp variant="identifier">{session.id}</Stamp>
          {blockerLabel && !isOffTrack ? (
            <Stamp tone="rule" variant="status">
              {blockerLabel}
            </Stamp>
          ) : null}
        </div>
        <span className="font-mono text-[10px] text-(--color-ink-3)">{session.agent}</span>
      </div>
      <div className="mt-1 truncate font-sans text-[13px] font-medium text-(--color-ink)">
        {session.name || `Session ${session.id}`}
      </div>
      {state ? (
        <div className="mt-1.5 flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-2 rounded-full"
            aria-hidden
            style={{ background: stageColor }}
          />
          <span
            className={
              isOffTrack
                ? "font-mono text-[10px] font-semibold text-(--color-rule) uppercase tracking-[0.06em]"
                : "font-mono text-[10px] font-semibold uppercase tracking-[0.06em]"
            }
            style={isOffTrack ? undefined : { color: stageColor }}
          >
            {state.replace(/_/g, " ")}
          </span>
        </div>
      ) : null}
    </Link>
  );
}

function UnassignedIssueRow({ issue, projectId }: { issue: IssueSummary; projectId: string }) {
  return (
    <Link
      to={`/p/${projectId}/issues/${issue.id}`}
      aria-label={`Issue ${issue.id}`}
      className="block rounded-(--radius-stamp) border border-(--color-edge) border-dashed bg-(--color-paper) px-3 py-2 transition-colors hover:border-(--color-ink-3)"
    >
      <div className="flex items-center justify-between gap-2">
        <Stamp variant="identifier">{issue.id}</Stamp>
        <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.06em]">
          {issue.status.replace(/_/g, " ")}
        </span>
      </div>
      <div className="mt-1 truncate font-sans text-[13px] font-medium text-(--color-ink)">
        {issue.title}
      </div>
    </Link>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="py-5 text-center font-serif text-[13px] italic text-(--color-ink-3)">
      {children}
    </div>
  );
}
