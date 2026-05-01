import { Link, useParams } from "react-router-dom";

import { MarkdownBody } from "@/components/MarkdownBody";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { toMarkdownRefs, useIssue } from "@/lib/api/endpoints/issues";
import { IssueBadges } from "./IssueBadges";
import { IssueHeader } from "./IssueHeader";
import { IssueRefsPanel } from "./IssueRefsPanel";
import { IssueTimeline } from "./IssueTimeline";
import { QuickActions } from "./QuickActions";

export function IssueDetail() {
  const { projectId, key } = useParams<{ projectId: string; key: string }>();
  if (!projectId || !key) {
    return <NotFound projectId={projectId} />;
  }
  return <IssueDetailInner projectId={projectId} issueKey={key} />;
}

function IssueDetailInner({ projectId, issueKey }: { projectId: string; issueKey: string }) {
  const { data: issue, isLoading, error } = useIssue(projectId, issueKey);

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
        Failed to load issue: {error instanceof Error ? error.message : "unknown error"}
      </div>
    );
  }

  if (!issue) {
    return <NotFound projectId={projectId} />;
  }

  return (
    <article className="flex flex-col gap-6 p-8">
      <IssueHeader issue={issue} projectId={projectId} />
      <IssueBadges issue={issue} />
      <QuickActions issue={issue} projectId={projectId} />
      <Separator />
      <section aria-labelledby="issue-body-heading" className="min-h-0">
        <h2 id="issue-body-heading" className="sr-only">
          Body
        </h2>
        {issue.body ? (
          <MarkdownBody
            content={issue.body}
            projectId={projectId}
            refs={toMarkdownRefs(issue.refs)}
          />
        ) : (
          <p className="text-sm text-muted-foreground italic">This issue has no body.</p>
        )}
      </section>
      <Separator />
      <div className="grid gap-6 md:grid-cols-2">
        <IssueRefsPanel refs={issue.refs} projectId={projectId} />
        <IssueTimeline
          createdAt={issue.created_at ?? undefined}
          updatedAt={issue.updated_at ?? undefined}
        />
      </div>
    </article>
  );
}

function NotFound({ projectId }: { projectId?: string }) {
  const boardHref = projectId ? `/p/${projectId}/board` : "/";
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-foreground">Issue not found</h1>
      <p className="mt-2 text-muted-foreground">This issue doesn't exist in this project.</p>
      <Link to={boardHref} className="mt-4 inline-block text-sm underline">
        ← Back to board
      </Link>
    </div>
  );
}
