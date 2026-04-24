import { Badge } from "@/components/ui/badge";
import type { IssueDetail } from "@/lib/api/endpoints/issues";

interface IssueBadgesProps {
  issue: IssueDetail;
}

export function IssueBadges({ issue }: IssueBadgesProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant="default" data-badge="status">
        {issue.status}
      </Badge>
      <Badge variant="secondary" data-badge="priority">
        priority: {issue.priority}
      </Badge>
      <Badge variant="secondary" data-badge="executor">
        executor: {issue.executor}
      </Badge>
      {issue.agent ? (
        <Badge variant="outline" data-badge="agent">
          agent: {issue.agent}
        </Badge>
      ) : null}
      {issue.labels.map((label) => (
        <Badge key={label} variant="outline" data-badge="label">
          {label}
        </Badge>
      ))}
      {issue.repo ? (
        <span className="text-xs text-muted-foreground" data-meta="repo">
          repo: {issue.repo}
        </span>
      ) : null}
    </div>
  );
}
