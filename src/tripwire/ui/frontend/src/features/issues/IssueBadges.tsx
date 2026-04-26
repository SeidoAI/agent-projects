import { Stamp } from "@/components/ui/stamp";
import type { IssueDetail } from "@/lib/api/endpoints/issues";

interface IssueBadgesProps {
  issue: IssueDetail;
}

export function IssueBadges({ issue }: IssueBadgesProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Stamp tone="default" data-badge="status">
        {issue.status}
      </Stamp>
      <Stamp tone="info" data-badge="priority">
        priority: {issue.priority}
      </Stamp>
      <Stamp tone="info" data-badge="executor">
        executor: {issue.executor}
      </Stamp>
      {issue.agent ? <Stamp data-badge="agent">agent: {issue.agent}</Stamp> : null}
      {issue.labels.map((label) => (
        <Stamp key={label} data-badge="label">
          {label}
        </Stamp>
      ))}
      {issue.repo ? (
        <span className="text-xs text-muted-foreground" data-meta="repo">
          repo: {issue.repo}
        </span>
      ) : null}
    </div>
  );
}
