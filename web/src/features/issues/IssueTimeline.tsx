interface IssueTimelineProps {
  createdAt?: string;
  updatedAt?: string;
}

function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function IssueTimeline({ createdAt, updatedAt }: IssueTimelineProps) {
  return (
    <section aria-labelledby="issue-timeline-heading" className="space-y-2">
      <h2 id="issue-timeline-heading" className="text-sm font-semibold text-foreground">
        Timeline
      </h2>
      <ul className="space-y-1 text-sm text-muted-foreground">
        {createdAt ? (
          <li>
            <span className="text-foreground">created</span> {formatTimestamp(createdAt)}
          </li>
        ) : null}
        {updatedAt ? (
          <li>
            <span className="text-foreground">updated</span> {formatTimestamp(updatedAt)}
          </li>
        ) : null}
      </ul>
      <p className="text-xs text-muted-foreground italic">Comments timeline ships in v2.</p>
    </section>
  );
}
