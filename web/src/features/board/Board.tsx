import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { EntityPreviewDrawer } from "@/components/ui/entity-preview-drawer";
import { InboxPreviewDrawer } from "@/components/ui/inbox-preview-drawer";
import { Stamp } from "@/components/ui/stamp";
import { useIssueStatusEnum, useIssues } from "@/features/issues/hooks/useIssues";
import type { IssueSummary } from "@/lib/api/endpoints/issues";
import { type SessionSummary, useSessions } from "@/lib/api/endpoints/sessions";
import { cn } from "@/lib/utils";
import { FilterPills } from "./FilterPills";
import { useBlockedInbox } from "./hooks/useBlockedInbox";
import { ageBucket, useBoardFilters } from "./hooks/useBoardFilters";
import { IssuesView } from "./IssuesView";
import { SessionsView } from "./SessionsView";

/**
 * v0.8 Board — operational view of everything in flight.
 *
 * Composes the building blocks:
 *  - `<FilterPills>` — multi-select filter pills, URL-persisted via
 *    `useBoardFilters`.
 *  - `<SessionsView>` / `<IssuesView>` — the active view's columns
 *    + drag-and-drop wiring.
 *  - `<EntityPreviewDrawer>` — opens when a card body is clicked,
 *    or `<InboxPreviewDrawer>` when an inbox cross-link is clicked.
 *
 * Sessions view is the default per spec §3.3. The toggle preserves
 * filter state across switches by keeping all params in the same
 * URL — no extra plumbing required.
 */
export function Board() {
  const { projectId } = useProjectShell();
  const sessionsQuery = useSessions(projectId);
  const issuesQuery = useIssues(projectId);
  const statusEnumQuery = useIssueStatusEnum(projectId);
  const blockedInbox = useBlockedInbox(projectId);
  const boardFilters = useBoardFilters();
  const { filters } = boardFilters;
  const [drawer, setDrawer] = useState<DrawerTarget>(null);

  const sessions = sessionsQuery.data ?? [];
  const issues = issuesQuery.data ?? [];

  const filteredSessions = useMemo(
    () => filterSessions(sessions, filters, blockedInbox.bySession),
    [sessions, filters, blockedInbox.bySession],
  );
  const filteredIssues = useMemo(
    () => filterIssues(issues, filters, blockedInbox.byIssue),
    [issues, filters, blockedInbox.byIssue],
  );

  const agentOptions = useMemo(() => {
    const set = new Set<string>();
    for (const s of sessions) if (s.agent) set.add(s.agent);
    for (const i of issues) if (i.agent) set.add(i.agent);
    return [...set].sort();
  }, [sessions, issues]);
  const ownerOptions = useMemo(() => {
    const set = new Set<string>();
    for (const i of issues) set.add(i.executor);
    return [...set].sort();
  }, [issues]);
  const ageOptions = ["today", "this-week", "this-month", "older"];

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 px-5 py-4">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="m-0 font-sans font-semibold text-[24px] text-(--color-ink) leading-tight tracking-[-0.01em]">
            Board
          </h1>
          <p className="mt-0.5 font-serif text-[14px] text-(--color-ink-2) italic">
            everything in flight, by station
          </p>
        </div>
        <ViewToggle
          value={filters.view}
          onChange={boardFilters.setView}
          sessionsCount={filteredSessions.length}
          issuesCount={filteredIssues.length}
        />
      </header>

      <FilterPills
        agents={agentOptions}
        owners={ownerOptions}
        ages={ageOptions}
        selectedAgents={filters.agents}
        selectedOwners={filters.owners}
        selectedAges={filters.ages}
        hasBlockedInbox={filters.hasBlockedInbox}
        blocked={filters.blocked}
        onToggleAgent={boardFilters.toggleAgent}
        onToggleOwner={boardFilters.toggleOwner}
        onToggleAge={boardFilters.toggleAge}
        onToggleBlockedInbox={boardFilters.toggleBlockedInbox}
        onToggleBlocked={boardFilters.toggleBlocked}
        onClearAll={boardFilters.clearAll}
      />

      {filters.view === "sessions" ? (
        <div className="min-h-0 flex-1">
          <SessionsView
            sessions={filteredSessions}
            blockedInbox={blockedInbox}
            activeStages={null}
            onCardClick={(s) => setDrawer({ kind: "session", session: s })}
            onCrossLinkClick={(s) => openInbox(s.id, blockedInbox.bySession.get(s.id), setDrawer)}
          />
        </div>
      ) : (
        <div className="min-h-0 flex-1">
          <IssuesView
            projectId={projectId}
            issues={filteredIssues}
            statusValues={statusEnumQuery.data?.values ?? []}
            blockedInbox={blockedInbox}
            onCardClick={(i) => setDrawer({ kind: "issue", issue: i })}
            onCrossLinkClick={(i) => openInbox(i.id, blockedInbox.byIssue.get(i.id), setDrawer)}
          />
        </div>
      )}

      <BoardDrawer projectId={projectId} target={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}

type DrawerTarget =
  | { kind: "session"; session: SessionSummary }
  | { kind: "issue"; issue: IssueSummary }
  | { kind: "inbox"; entryId: string }
  | null;

function openInbox(
  _entityId: string,
  entries: { id: string }[] | undefined,
  setDrawer: (t: DrawerTarget) => void,
) {
  // Multiple open BLOCKED entries can reference the same entity;
  // open the first one (most recent — backend returns reverse-chrono
  // ordering by default). The drawer's "Next →" affordance is a
  // fast-follow if PMs find this insufficient.
  const first = entries?.[0];
  if (!first) return;
  setDrawer({ kind: "inbox", entryId: first.id });
}

function ViewToggle({
  value,
  onChange,
  sessionsCount,
  issuesCount,
}: {
  value: "sessions" | "issues";
  onChange: (v: "sessions" | "issues") => void;
  sessionsCount: number;
  issuesCount: number;
}) {
  return (
    <fieldset
      aria-label="Board view"
      className="m-0 inline-flex items-center gap-0 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) p-0.5"
    >
      <ToggleButton active={value === "sessions"} onClick={() => onChange("sessions")}>
        sessions · {sessionsCount}
      </ToggleButton>
      <ToggleButton active={value === "issues"} onClick={() => onChange("issues")}>
        issues · {issuesCount}
      </ToggleButton>
    </fieldset>
  );
}

function ToggleButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-(--radius-stamp) px-3 py-1 font-mono text-[11px] tracking-[0.06em] transition-colors",
        active
          ? "bg-(--color-ink) text-(--color-paper)"
          : "text-(--color-ink-3) hover:text-(--color-ink)",
      )}
    >
      {children}
    </button>
  );
}

function BoardDrawer({
  projectId,
  target,
  onClose,
}: {
  projectId: string;
  target: DrawerTarget;
  onClose: () => void;
}) {
  if (!target) {
    // Render the inbox drawer in its closed state so its hooks stay
    // mounted (avoids tearing the inbox query down when the user
    // closes only to reopen seconds later).
    return <InboxPreviewDrawer projectId={projectId} entryId={null} onClose={onClose} />;
  }
  if (target.kind === "inbox") {
    return <InboxPreviewDrawer projectId={projectId} entryId={target.entryId} onClose={onClose} />;
  }
  if (target.kind === "session") {
    return (
      <EntityPreviewDrawer
        open={true}
        onClose={onClose}
        title={target.session.name}
        headerSlot={
          <div className="flex flex-wrap items-center gap-2">
            <Stamp variant="identifier" tone="default">
              {target.session.id}
            </Stamp>
            <Stamp variant="status" tone="default">
              {target.session.status}
            </Stamp>
          </div>
        }
        topRightSlot={
          <Link
            to={`/p/${projectId}/sessions/${target.session.id}`}
            className="font-mono text-[10px] text-(--color-ink-3) hover:text-(--color-ink) tracking-[0.06em]"
          >
            open full →
          </Link>
        }
        body={<SessionDrawerBody session={target.session} />}
      />
    );
  }
  // issue
  return (
    <EntityPreviewDrawer
      open={true}
      onClose={onClose}
      title={target.issue.title}
      headerSlot={
        <div className="flex flex-wrap items-center gap-2">
          <Stamp variant="identifier" tone="default">
            {target.issue.id}
          </Stamp>
          <Stamp variant="status" tone="default">
            {target.issue.status}
          </Stamp>
        </div>
      }
      topRightSlot={
        <Link
          to={`/p/${projectId}/issues/${target.issue.id}`}
          className="font-mono text-[10px] text-(--color-ink-3) hover:text-(--color-ink) tracking-[0.06em]"
        >
          open full →
        </Link>
      }
      body={<IssueDrawerBody issue={target.issue} />}
    />
  );
}

function SessionDrawerBody({ session }: { session: SessionSummary }) {
  return (
    <dl className="flex flex-col gap-3 font-mono text-[12px] text-(--color-ink) tracking-[0.04em]">
      <Pair label="agent" value={session.agent} />
      <Pair label="status" value={session.status} />
      <Pair label="estimated size" value={session.estimated_size ?? "—"} />
      <Pair label="re-engagement count" value={String(session.re_engagement_count)} />
      <Pair
        label="task progress"
        value={`${session.task_progress.done} / ${session.task_progress.total}`}
      />
      <Pair
        label="blocked by"
        value={
          session.blocked_by_sessions.length === 0 ? "—" : session.blocked_by_sessions.join(", ")
        }
      />
      <Pair label="issues" value={session.issues.length === 0 ? "—" : session.issues.join(", ")} />
    </dl>
  );
}

function IssueDrawerBody({ issue }: { issue: IssueSummary }) {
  return (
    <dl className="flex flex-col gap-3 font-mono text-[12px] text-(--color-ink) tracking-[0.04em]">
      <Pair label="status" value={issue.status} />
      <Pair label="priority" value={issue.priority} />
      <Pair label="executor" value={issue.executor} />
      <Pair label="agent" value={issue.agent ?? "—"} />
      <Pair label="parent" value={issue.parent ?? "—"} />
      <Pair label="repo" value={issue.repo ?? "—"} />
      <Pair
        label="blocked by"
        value={issue.blocked_by.length === 0 ? "—" : issue.blocked_by.join(", ")}
      />
      <Pair label="labels" value={issue.labels.length === 0 ? "—" : issue.labels.join(", ")} />
    </dl>
  );
}

function Pair({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="w-32 shrink-0 text-(--color-ink-3) text-[10px] uppercase tracking-[0.18em]">
        {label}
      </dt>
      <dd className="m-0 text-(--color-ink)">{value}</dd>
    </div>
  );
}

function filterSessions(
  sessions: SessionSummary[],
  filters: ReturnType<typeof useBoardFilters>["filters"],
  blockedSessions: Map<string, unknown[]>,
): SessionSummary[] {
  return sessions.filter((s) => {
    if (filters.agents.size > 0 && !filters.agents.has(s.agent)) return false;
    if (filters.ages.size > 0) {
      // SessionSummary has no created_at; the dashboard uses last
      // engagement timestamp via current_state. Without a per-session
      // timestamp surfaced on this DTO we approximate by skipping the
      // age filter for sessions — the filter still constrains issues
      // which DO have created_at, and the absence here is captured
      // in decisions.md if it becomes a regression source.
    }
    if (filters.hasBlockedInbox && !blockedSessions.has(s.id)) return false;
    if (filters.blocked && s.blocked_by_sessions.length === 0) return false;
    return true;
  });
}

function filterIssues(
  issues: IssueSummary[],
  filters: ReturnType<typeof useBoardFilters>["filters"],
  blockedIssues: Map<string, unknown[]>,
): IssueSummary[] {
  return issues.filter((i) => {
    if (filters.agents.size > 0 && !(i.agent && filters.agents.has(i.agent))) return false;
    if (filters.owners.size > 0 && !filters.owners.has(i.executor)) return false;
    if (filters.ages.size > 0 && !filters.ages.has(ageBucket(i.created_at))) return false;
    if (filters.hasBlockedInbox && !blockedIssues.has(i.id)) return false;
    if (filters.blocked && !i.is_blocked) return false;
    return true;
  });
}
