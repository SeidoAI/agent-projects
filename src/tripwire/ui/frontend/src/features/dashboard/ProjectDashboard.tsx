import { Link, useParams } from "react-router-dom";

import { useProjectShell } from "@/app/ProjectShell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useProject } from "@/lib/api/endpoints/project";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import type { StatusCount } from "./hooks/useProjectStats";
import { useProjectStats } from "./hooks/useProjectStats";

export function ProjectDashboard() {
  const { projectId } = useProjectShell();
  const project = useProject(projectId);
  const stats = useProjectStats(projectId);

  return (
    <div className="p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-foreground">
          {project.data?.name ?? projectId}
        </h1>
        <p className="text-sm text-muted-foreground">
          {stats.isLoading
            ? "Loading…"
            : `${stats.totalIssues} issue${stats.totalIssues === 1 ? "" : "s"}`}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold uppercase text-muted-foreground">
            Issue status
          </h2>
          <StatusCountGrid counts={stats.statusCounts} isLoading={stats.isLoading} />
        </section>

        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase text-muted-foreground">Phase</h2>
          <PhaseCard phase={project.data?.phase} isLoading={project.isLoading} />
        </section>

        <section className="lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold uppercase text-muted-foreground">
            Recent sessions
          </h2>
          <RecentSessionsCard sessions={stats.recentSessions} isLoading={stats.isLoading} />
        </section>

        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase text-muted-foreground">Shortcuts</h2>
          <ShortcutsCard />
        </section>
      </div>
    </div>
  );
}

function StatusCountGrid({ counts, isLoading }: { counts: StatusCount[]; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[0, 1, 2, 3].map((n) => (
          <Skeleton key={n} className="h-20" />
        ))}
      </div>
    );
  }
  if (counts.length === 0) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-muted-foreground">
          No statuses configured. Add one to <code>enums/issue_status.yaml</code>.
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {counts.map((c) => (
        <StatusCountCard key={c.value} count={c} />
      ))}
    </div>
  );
}

function StatusCountCard({ count }: { count: StatusCount }) {
  const { projectId } = useParams();
  // Each card deep-links to the board filtered by this status. The
  // kanban reads `?status=` from the URL.
  const href = `/p/${projectId}/board?status=${encodeURIComponent(count.value)}`;
  return (
    <Link
      to={href}
      aria-label={`${count.count} issues in status ${count.label}`}
      className="block rounded-lg border bg-card p-4 text-card-foreground shadow-sm transition-colors hover:border-primary/40"
    >
      <div className="flex items-center justify-between">
        <span
          className="inline-flex h-2 w-2 rounded-full"
          style={{ backgroundColor: count.color ?? "currentColor" }}
          aria-hidden
        />
        <span className="text-2xl font-semibold tabular-nums">{count.count}</span>
      </div>
      <div className="mt-2 text-sm text-muted-foreground">{count.label}</div>
    </Link>
  );
}

function PhaseCard({ phase, isLoading }: { phase: string | undefined; isLoading: boolean }) {
  if (isLoading) return <Skeleton className="h-24" />;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base capitalize">{phase ?? "unknown"}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{describePhase(phase)}</p>
      </CardContent>
    </Card>
  );
}

function describePhase(phase: string | undefined): string {
  switch (phase) {
    case "scoping":
      return "Defining what needs to be built.";
    case "scoped":
      return "Ready for execution.";
    case "executing":
      return "Sessions are in flight.";
    case "reviewing":
      return "Work is under review.";
    default:
      return "No phase set.";
  }
}

function RecentSessionsCard({
  sessions,
  isLoading,
}: {
  sessions: SessionSummary[];
  isLoading: boolean;
}) {
  const { projectId } = useParams();
  if (isLoading) return <Skeleton className="h-40" />;
  if (sessions.length === 0) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-muted-foreground">
          No sessions yet. Start one with <code>tripwire session start</code>.
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardContent className="pt-6">
        <ul className="divide-y divide-border">
          {sessions.map((s) => (
            <li key={s.id} className="flex items-center justify-between py-2 first:pt-0 last:pb-0">
              <Link
                to={`/p/${projectId}/sessions/${s.id}`}
                className="min-w-0 flex-1 truncate text-sm text-foreground hover:underline"
              >
                {s.name || s.id}
              </Link>
              <div className="ml-3 flex items-center gap-2">
                <Badge variant="secondary" className="text-[10px]">
                  {s.agent}
                </Badge>
                <span className="text-xs text-muted-foreground">{s.status}</span>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function ShortcutsCard() {
  const { projectId } = useParams();
  const shortcuts = [
    { to: `/p/${projectId}/board`, label: "Open board", hint: "Track active work" },
    { to: `/p/${projectId}/graph`, label: "Concept graph", hint: "See how the pieces connect" },
    { to: `/p/${projectId}/sessions`, label: "Sessions", hint: "All recent work" },
  ];
  return (
    <Card>
      <CardContent className="pt-6">
        <ul className="space-y-2">
          {shortcuts.map((s) => (
            <li key={s.to}>
              <Link
                to={s.to}
                className="block rounded-md p-2 transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <span className="text-sm font-medium">{s.label}</span>
                <span className="ml-2 text-xs text-muted-foreground">{s.hint}</span>
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
