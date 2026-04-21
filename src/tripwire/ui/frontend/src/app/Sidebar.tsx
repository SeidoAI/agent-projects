export function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col gap-6 border-r border-border bg-background p-4">
      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Issues</h2>
        <p className="text-sm text-muted-foreground">0 issues</p>
      </section>
      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Nodes</h2>
        <p className="text-sm text-muted-foreground">0 nodes</p>
      </section>
      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
          Quick actions
        </h2>
        <p className="text-sm text-muted-foreground">No actions available</p>
      </section>
    </aside>
  );
}
