export function AgentStatusBar() {
  // Skeleton — placeholder for v2 live data. Wired in KUI-66.
  return (
    <div className="flex items-center gap-2 border-t border-border bg-background px-4 py-1.5 text-xs text-muted-foreground">
      <span>0 agents running</span>
      <span>·</span>
      <span>file watcher: connected</span>
    </div>
  );
}
