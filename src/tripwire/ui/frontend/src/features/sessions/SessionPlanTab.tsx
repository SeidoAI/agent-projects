import { MarkdownBody } from "@/components/MarkdownBody";

interface SessionPlanTabProps {
  planMd: string;
  projectId: string;
}

export function SessionPlanTab({ planMd, projectId }: SessionPlanTabProps) {
  if (!planMd.trim()) {
    return (
      <p className="text-sm text-muted-foreground italic">No plan.md recorded for this session.</p>
    );
  }
  return <MarkdownBody content={planMd} projectId={projectId} />;
}
