export function ValidationStatusIndicator() {
  // Skeleton — hardcoded green dot + "valid". Filled in by KUI-65.
  return (
    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
      <span className="h-2 w-2 rounded-full bg-status-done" />
      valid
    </div>
  );
}
