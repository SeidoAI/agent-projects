import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import type { SessionSummary } from "@/lib/api/endpoints/sessions";
import { TaskProgressBar } from "./TaskProgressBar";

interface SessionCardProps {
  session: SessionSummary;
  projectId: string;
}

export function SessionCard({ session, projectId }: SessionCardProps) {
  return (
    <Link
      to={`/p/${projectId}/sessions/${session.id}`}
      className="block rounded-md border bg-background p-4 shadow-sm transition-colors hover:border-foreground/30"
      data-session-id={session.id}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-foreground">{session.name}</h3>
          <p className="text-xs text-muted-foreground">
            {session.id} · {session.agent}
          </p>
        </div>
        <Badge variant="outline" data-badge="status">
          {session.status}
        </Badge>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{session.issues.length} issues</span>
        {session.estimated_size ? <span>· size: {session.estimated_size}</span> : null}
      </div>

      {session.blocked_by_sessions.length > 0 ? (
        <p className="mt-1 text-xs text-amber-500" data-field="blocked-by">
          blocked by: {session.blocked_by_sessions.join(", ")}
        </p>
      ) : null}

      <div className="mt-3">
        <TaskProgressBar progress={session.task_progress} />
      </div>
    </Link>
  );
}
