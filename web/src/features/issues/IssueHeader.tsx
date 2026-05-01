import { Link } from "react-router-dom";

import type { IssueDetail } from "@/lib/api/endpoints/issues";

interface IssueHeaderProps {
  issue: IssueDetail;
  projectId: string;
}

export function IssueHeader({ issue, projectId }: IssueHeaderProps) {
  return (
    <header className="space-y-1">
      <h1 className="text-2xl font-semibold text-foreground">
        <span className="text-muted-foreground">{issue.id}</span>
        <span className="mx-2 text-muted-foreground">·</span>
        <span>{issue.title}</span>
      </h1>
      {issue.parent ? (
        <p className="text-sm text-muted-foreground">
          Epic:{" "}
          <Link
            to={`/p/${projectId}/issues/${issue.parent}`}
            className="underline decoration-dotted hover:text-foreground"
          >
            {issue.parent}
          </Link>
        </p>
      ) : null}
    </header>
  );
}
