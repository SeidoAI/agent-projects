import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useIssue } from "@/lib/api/endpoints/issues";

interface SessionIssuesTabProps {
  issueKeys: string[];
  projectId: string;
  groupingRationale: string | null;
}

interface IssueRowProps {
  projectId: string;
  issueKey: string;
}

function IssueRow({ projectId, issueKey }: IssueRowProps) {
  const { data, isLoading } = useIssue(projectId, issueKey);
  return (
    <TableRow data-issue-key={issueKey}>
      <TableCell className="font-mono text-sm">
        <Link
          to={`/p/${projectId}/issues/${issueKey}`}
          className="underline decoration-dotted hover:decoration-solid"
        >
          {issueKey}
        </Link>
      </TableCell>
      <TableCell className="text-sm">
        {isLoading ? (
          <span className="text-muted-foreground">…</span>
        ) : data ? (
          data.title
        ) : (
          <span className="text-muted-foreground italic">unknown</span>
        )}
      </TableCell>
      <TableCell>
        {isLoading ? (
          <span className="text-xs text-muted-foreground">…</span>
        ) : data ? (
          <Badge variant="outline" className="text-xs">
            {data.status}
          </Badge>
        ) : null}
      </TableCell>
    </TableRow>
  );
}

export function SessionIssuesTab({
  issueKeys,
  projectId,
  groupingRationale,
}: SessionIssuesTabProps) {
  return (
    <div className="space-y-3">
      {groupingRationale ? (
        <blockquote className="border-l-4 border-primary/30 pl-3 text-sm text-muted-foreground italic">
          {groupingRationale}
        </blockquote>
      ) : null}
      {issueKeys.length === 0 ? (
        <p className="text-sm text-muted-foreground">No issues in this session.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-32">Key</TableHead>
              <TableHead>Title</TableHead>
              <TableHead className="w-32">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {issueKeys.map((key) => (
              <IssueRow key={key} projectId={projectId} issueKey={key} />
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
