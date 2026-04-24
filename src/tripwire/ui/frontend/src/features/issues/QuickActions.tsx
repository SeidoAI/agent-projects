import { CheckCheck, ChevronDown, FileCode2, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ApiError } from "@/lib/api/client";
import { type IssueDetail, useIssuePatch, useIssueValidate } from "@/lib/api/endpoints/issues";
import { useProject } from "@/lib/api/endpoints/project";

interface QuickActionsProps {
  issue: IssueDetail;
  projectId: string;
}

export function QuickActions({ issue, projectId }: QuickActionsProps) {
  const { data: project } = useProject(projectId);
  const patch = useIssuePatch(projectId, issue.id);
  const validate = useIssueValidate(projectId, issue.id);

  const transitions = project?.status_transitions?.[issue.status] ?? [];

  function onStatusClick(next: string) {
    patch.mutate(
      { status: next },
      {
        onSuccess: () => {
          toast.success(`Status → ${next}`);
        },
        onError: (err) => {
          const msg = err instanceof ApiError ? err.message : "Status change failed.";
          toast.error(msg);
        },
      },
    );
  }

  function onValidateClick() {
    validate.mutate(undefined, {
      onSuccess: (report) => {
        const errors = report.errors ?? 0;
        const warnings = report.warnings ?? 0;
        const codeSummary = (report.codes ?? []).map((c) => `${c.code}×${c.count}`).join(", ");
        const body = codeSummary
          ? `${errors} errors · ${warnings} warnings — ${codeSummary}`
          : `${errors} errors · ${warnings} warnings`;
        if (errors === 0) {
          toast.success(body);
        } else {
          toast.error(body);
        }
      },
      onError: (err) => {
        const msg = err instanceof ApiError ? err.message : "Validation failed.";
        toast.error(msg);
      },
    });
  }

  const editorPath = project?.dir ? `file://${project.dir}/issues/${issue.id}/issue.yaml` : null;

  return (
    <div className="flex items-center gap-2" data-testid="issue-quick-actions">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            disabled={patch.isPending || transitions.length === 0}
          >
            Change status
            <ChevronDown className="ml-1 h-3.5 w-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {transitions.length === 0 ? (
            <DropdownMenuItem disabled>No valid transitions</DropdownMenuItem>
          ) : (
            transitions.map((next) => (
              <DropdownMenuItem key={next} onSelect={() => onStatusClick(next)}>
                {next}
              </DropdownMenuItem>
            ))
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <Button variant="outline" size="sm" onClick={onValidateClick} disabled={validate.isPending}>
        {validate.isPending ? (
          <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
        ) : (
          <CheckCheck className="mr-1 h-3.5 w-3.5" />
        )}
        Validate
      </Button>

      {editorPath ? (
        <Button asChild variant="outline" size="sm">
          <a
            href={editorPath}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Open issue YAML in editor"
          >
            <FileCode2 className="mr-1 h-3.5 w-3.5" />
            Open in editor
          </a>
        </Button>
      ) : null}
    </div>
  );
}
