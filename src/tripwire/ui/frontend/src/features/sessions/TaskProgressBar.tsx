import type { TaskProgress } from "@/lib/api/endpoints/sessions";
import { cn } from "@/lib/utils";

interface TaskProgressBarProps {
  progress: TaskProgress;
  className?: string;
}

export function TaskProgressBar({ progress, className }: TaskProgressBarProps) {
  const { done, total } = progress;
  if (total === 0) {
    return (
      <p
        className={cn("text-xs text-muted-foreground italic", className)}
        data-testid="task-progress-empty"
      >
        No tasks tracked.
      </p>
    );
  }
  const pct = Math.round((done / total) * 100);
  return (
    <div
      className={cn("flex items-center gap-2", className)}
      data-testid="task-progress"
      data-done={done}
      data-total={total}
    >
      <div
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${done} of ${total} tasks done`}
      >
        <div className="h-full bg-emerald-500 transition-[width]" style={{ width: `${pct}%` }} />
      </div>
      <span className="whitespace-nowrap text-xs text-muted-foreground">
        {done}/{total}
      </span>
    </div>
  );
}
