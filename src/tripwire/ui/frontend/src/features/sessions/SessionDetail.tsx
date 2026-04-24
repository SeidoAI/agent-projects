import { Link, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api/client";
import { useSession } from "@/lib/api/endpoints/sessions";
import { ArtifactList } from "../artifacts/ArtifactList";
import { SessionIssuesTab } from "./SessionIssuesTab";
import { SessionPlanTab } from "./SessionPlanTab";
import { SessionReposTab } from "./SessionReposTab";
import { TaskProgressBar } from "./TaskProgressBar";

export function SessionDetail() {
  const { projectId, sid } = useParams<{ projectId: string; sid: string }>();
  if (!projectId || !sid) return <NotFound projectId={projectId} />;
  return <SessionDetailInner projectId={projectId} sid={sid} />;
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
      <div className="p-8 text-sm text-red-500" role="alert">
        Failed to load session.
      </div>
    );
  }

  if (!session) return <NotFound projectId={projectId} />;

  return (
    <article className="flex flex-col gap-4 p-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold text-foreground">{session.name}</h1>
          <Badge variant="outline" data-badge="status">
            {session.status}
          </Badge>
          {session.estimated_size ? (
            <Badge variant="secondary">size: {session.estimated_size}</Badge>
          ) : null}
          <span className="ml-auto text-xs text-muted-foreground">{session.id}</span>
        </div>
        {session.blocked_by_sessions.length > 0 ? (
          <p className="text-xs text-amber-500" data-field="blocked-by">
            blocked by: {session.blocked_by_sessions.join(", ")}
          </p>
        ) : null}
        <div className="max-w-md">
          <TaskProgressBar progress={session.task_progress} />
        </div>
      </header>

      <TooltipProvider>
        <Tabs defaultValue="plan" className="w-full" data-testid="session-tabs">
          <TabsList>
            <TabsTrigger value="plan">Plan</TabsTrigger>
            <TabsTrigger value="issues">Issues</TabsTrigger>
            <TabsTrigger value="repos">Repos</TabsTrigger>
            <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
          </TabsList>

          <TabsContent value="plan" className="mt-4">
            <SessionPlanTab planMd={session.plan_md} projectId={projectId} />
          </TabsContent>

          <TabsContent value="issues" className="mt-4">
            <SessionIssuesTab
              issueKeys={session.issues}
              projectId={projectId}
              groupingRationale={session.grouping_rationale}
            />
          </TabsContent>

          <TabsContent value="repos" className="mt-4">
            <SessionReposTab repos={session.repos} />
          </TabsContent>

          <TabsContent value="artifacts" className="mt-4">
            <ArtifactList projectId={projectId} sessionId={sid} />
          </TabsContent>
        </Tabs>
      </TooltipProvider>
    </article>
  );
}

function NotFound({ projectId }: { projectId?: string }) {
  const sessionsHref = projectId ? `/p/${projectId}/sessions` : "/projects";
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-foreground">Session not found</h1>
      <Link to={sessionsHref} className="mt-4 inline-block text-sm underline">
        ← Back to sessions
      </Link>
    </div>
  );
}
