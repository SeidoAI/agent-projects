import { Link } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { LifecycleWire } from "@/components/ui/lifecycle-wire";
import { MarginNote } from "@/components/ui/margin-note";
import { Stamp } from "@/components/ui/stamp";
import { type ProcessEvent, useWorkflowEvents } from "@/lib/api/endpoints/events";
import { useProject } from "@/lib/api/endpoints/project";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { useProjectStats } from "./hooks/useProjectStats";

/**
 * Project Dashboard — first thing the PM sees (per spec §3.2).
 *
 * Layout (1440×900): hero header, full-width LifecycleWire strip,
 * three-column body (Open Work | Recent Activity | Project Vitals),
 * footer rail with the latest reviewer note.
 *
 * Backend Strand Y endpoints may not be live yet; the centre column
 * gracefully renders an empty state when `useWorkflowEvents` resolves
 * undefined (404 retry-disabled per workflow.ts / events.ts client).
 */
const LIFECYCLE_STATIONS = [
  { id: "planned", label: "planned" },
  { id: "queued", label: "queued" },
  { id: "executing", label: "executing" },
  { id: "in_review", label: "review" },
  { id: "verified", label: "verified" },
  { id: "completed", label: "completed" },
];

export function ProjectDashboard() {
  const { projectId } = useProjectShell();
  const project = useProject(projectId);
  const stats = useProjectStats(projectId);
  const events = useWorkflowEvents(projectId, {
    limit: 6,
    kinds: ["tripwire_fire", "validator_fail", "artifact_rejected", "pm_review_opened"],
  });

  // Bucket sessions by station — the wire above shows counts, the left
  // column lists them. Sessions whose `current_state` doesn't map onto
  // a known station fall through silently (we can't render them on a
  // wire that doesn't have a slot for them).
  const sessions = stats.recentSessions;
  const counts: Record<string, number> = {};
  for (const s of sessions) {
    const station = s.current_state ?? "queued";
    counts[station] = (counts[station] ?? 0) + 1;
  }

  const heading = project.data?.name ?? projectId;
  const description = stats.isLoading
    ? null
    : describeProject(project.data?.phase, stats.totalIssues);

  return (
    <div className="bg-(--color-paper) px-7 pt-6 pb-8 text-(--color-ink)">
      <header className="flex items-end justify-between gap-6">
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
            <p className="mt-2 max-w-[720px] font-serif text-[17px] italic text-(--color-ink-2) leading-snug">
              {description}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-1.5 font-mono text-[11px] text-(--color-ink-3)">
          {project.data?.phase ? <Stamp tone="rule">phase · {project.data.phase}</Stamp> : null}
        </div>
      </header>

      <IssueStatusGrid
        statusCounts={stats.statusCounts}
        totalIssues={stats.totalIssues}
        projectId={projectId}
      />

      <div className="mt-4 rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) px-6 pt-5 pb-3">
        <div className="mb-2 flex items-baseline justify-between">
          <SectionTitle sub="every session, where it sits in the flow">
            Sessions across the lifecycle
          </SectionTitle>
        </div>
        <LifecycleWire stations={LIFECYCLE_STATIONS} counts={counts} height={96} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
        <LiveNowColumn sessions={sessions} projectId={projectId} />
        <ReviewsAndChecksColumn events={events.data?.events ?? []} projectId={projectId} />
      </div>
    </div>
  );
}

function describeProject(phase: string | undefined, totalIssues: number): string {
  const issueClause =
    totalIssues === 0 ? "no issues yet" : `${totalIssues} issues across the project`;
  switch (phase) {
    case "scoping":
      return `${issueClause} — defining what needs to be built.`;
    case "scoped":
      return `${issueClause} — ready for execution.`;
    case "executing":
      return `${issueClause} — sessions in flight, plans and edits running side by side.`;
    case "reviewing":
      return `${issueClause} — work under review.`;
    default:
      return `${issueClause}.`;
  }
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

function LiveNowColumn({ sessions, projectId }: { sessions: SessionSummary[]; projectId: string }) {
  return (
    <section className="rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <SectionTitle>Live now</SectionTitle>
        <span className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
          {sessions.length} session{sessions.length === 1 ? "" : "s"}
        </span>
      </div>
      {sessions.length === 0 ? (
        <Empty>no sessions running</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {sessions.map((s) => (
            <li key={s.id}>
              <SessionRow session={s} projectId={projectId} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SessionRow({ session, projectId }: { session: SessionSummary; projectId: string }) {
  return (
    <Link
      to={`/p/${projectId}/sessions/${session.id}`}
      aria-label={`Session ${session.id}`}
      className="block rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2 transition-colors hover:border-(--color-ink-3)"
    >
      <div className="flex items-center justify-between gap-2">
        <Stamp variant="identifier">{session.id}</Stamp>
        <span className="font-mono text-[10px] text-(--color-ink-3)">{session.agent}</span>
      </div>
      <div className="mt-1 truncate font-sans text-[13px] font-medium text-(--color-ink)">
        {session.name || `Session ${session.id}`}
      </div>
      {session.current_state ? (
        <div className="mt-1 font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.06em]">
          {session.current_state}
        </div>
      ) : null}
    </Link>
  );
}

function ReviewsAndChecksColumn({
  events,
  projectId,
}: {
  events: ProcessEvent[];
  projectId: string;
}) {
  return (
    <section className="rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <SectionTitle>Reviews &amp; checks</SectionTitle>
        <Link
          to={`/p/${projectId}/tripwires`}
          className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em] hover:text-(--color-ink)"
        >
          tripwire log →
        </Link>
      </div>
      {events.length === 0 ? (
        <Empty>no recent activity</Empty>
      ) : (
        <ul className="flex flex-col">
          {events.map((e) => (
            <li key={e.id}>
              <EventRow event={e} projectId={projectId} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function EventRow({ event, projectId }: { event: ProcessEvent; projectId: string }) {
  const tone = eventTone(event.kind);
  const summary = eventSummary(event);
  return (
    <Link
      to={`/p/${projectId}/tripwires?focus=${encodeURIComponent(event.id)}`}
      className="-mx-2 block border-(--color-edge) border-b border-dashed px-2 py-2 transition-colors hover:bg-(--color-paper-3)"
    >
      <div className="flex items-baseline justify-between gap-2">
        <Stamp tone={tone} variant="status">
          {event.kind.replace(/_/g, " ")}
        </Stamp>
        <span className="font-mono text-[10px] text-(--color-ink-3)">{event.fired_at}</span>
      </div>
      <div className="mt-1 font-sans text-[12.5px] text-(--color-ink)">{summary}</div>
      {event.evidence ? (
        <MarginNote className="mt-1 block text-[11.5px] text-(--color-ink-2)">
          {event.evidence}
        </MarginNote>
      ) : null}
    </Link>
  );
}

function eventTone(kind: ProcessEvent["kind"]): "rule" | "tripwire" | "info" | "default" {
  switch (kind) {
    case "tripwire_fire":
    case "validator_fail":
    case "artifact_rejected":
      return "rule";
    case "validator_pass":
      return "info";
    case "pm_review_opened":
    case "pm_review_closed":
      return "tripwire";
    default:
      return "default";
  }
}

function eventSummary(event: ProcessEvent): string {
  const sid = event.session_id;
  switch (event.kind) {
    case "tripwire_fire":
      return `${event.tripwire_id ?? "tripwire"} fired on ${sid}`;
    case "validator_fail":
      return `${event.validator_id ?? "validator"} failed on ${sid}`;
    case "validator_pass":
      return `${event.validator_id ?? "validator"} passed on ${sid}`;
    case "artifact_rejected":
      return `${event.artifact ?? "artifact"} rejected on ${sid}`;
    case "pm_review_opened":
      return `PM review opened on ${sid}`;
    case "pm_review_closed":
      return `PM review closed on ${sid}`;
    case "status_transition":
      return `status transition on ${sid}`;
    default:
      return sid;
  }
}

/**
 * Issue status — full-width horizontal grid of status pills, one per
 * enum value. Replaces the right-column "Project vitals" treatment;
 * matches `dashboard.jsx`'s IssueStatusGrid (full-width card, internal
 * row of pills). Each pill links to the board filtered to that status.
 *
 * `auto-fit + minmax` so the row stays comfortable across however many
 * statuses the project's `issue_status` enum exposes today (currently
 * 7 — backlog/todo/in_progress/in_review/verified/done/canceled), plus
 * any custom statuses a project might add later.
 */
function IssueStatusGrid({
  statusCounts,
  totalIssues,
  projectId,
}: {
  statusCounts: ReturnType<typeof useProjectStats>["statusCounts"];
  totalIssues: number;
  projectId: string;
}) {
  return (
    <section className="mt-6 rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) px-6 pt-5 pb-5">
      <div className="mb-3 flex items-baseline justify-between">
        <SectionTitle sub={`${totalIssues} issues across the project`}>Issue status</SectionTitle>
        <Link
          to={`/p/${projectId}/board`}
          className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em] hover:text-(--color-ink)"
        >
          jump to board →
        </Link>
      </div>
      {statusCounts.length === 0 ? (
        <Empty>no statuses configured</Empty>
      ) : (
        <ul
          className="grid gap-2.5"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}
        >
          {statusCounts.map((c) => (
            <li key={c.value}>
              <Link
                to={`/p/${projectId}/board?status=${encodeURIComponent(c.value)}`}
                aria-label={`${c.count} issues in status ${c.label}`}
                className="block rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-3 py-2.5 transition-colors hover:border-(--color-ink-3)"
              >
                <div className="flex items-center justify-between">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    aria-hidden
                    style={{ background: c.color ?? "currentColor" }}
                  />
                  <span className="font-sans font-semibold text-[24px] tabular-nums leading-none tracking-[-0.02em]">
                    {c.count}
                  </span>
                </div>
                <div className="mt-1.5 font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.06em]">
                  {c.label}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="py-5 text-center font-serif text-[13px] italic text-(--color-ink-3)">
      {children}
    </div>
  );
}
