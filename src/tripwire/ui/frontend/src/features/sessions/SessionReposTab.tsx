import type { RepoBinding } from "@/lib/api/endpoints/sessions";

interface SessionReposTabProps {
  repos: RepoBinding[];
}

export function SessionReposTab({ repos }: SessionReposTabProps) {
  if (repos.length === 0) {
    return <p className="text-sm text-muted-foreground">No repos bound to this session.</p>;
  }
  return (
    <ul className="space-y-3">
      {repos.map((r) => (
        <li key={r.repo} className="rounded-md border bg-background p-3" data-repo={r.repo}>
          <p className="font-mono text-sm">{r.repo}</p>
          <dl className="mt-1 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
            <dt>base branch</dt>
            <dd className="font-mono">{r.base_branch}</dd>
            <dt>session branch</dt>
            <dd className="font-mono">
              {r.branch ?? <span className="italic">unset (assigned at launch)</span>}
            </dd>
            <dt>PR</dt>
            <dd>
              {r.pr_number ? (
                <span className="font-mono">#{r.pr_number}</span>
              ) : (
                <span className="italic">not opened yet</span>
              )}
            </dd>
          </dl>
        </li>
      ))}
    </ul>
  );
}
