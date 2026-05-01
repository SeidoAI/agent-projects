import { useProjectShell } from "@/app/ProjectShell";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { type PhaseLogEntry, useProject } from "@/lib/api/endpoints/project";
import { cn } from "@/lib/utils";

type Phase = "scoping" | "scoped" | "executing" | "reviewing";

const PHASE_STYLES: Record<Phase, string> = {
  scoping: "bg-blue-500/15 text-blue-700 border-blue-500/30 dark:text-blue-300",
  scoped: "bg-violet-500/15 text-violet-700 border-violet-500/30 dark:text-violet-300",
  executing: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  reviewing: "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300",
};

const FALLBACK_STYLE = "bg-muted text-muted-foreground border-border";

function isKnownPhase(phase: string): phase is Phase {
  return phase in PHASE_STYLES;
}

export function PhaseBadge() {
  const { projectId } = useProjectShell();
  const { data, isLoading } = useProject(projectId);

  if (isLoading || !data) {
    return (
      <span
        role="status"
        aria-label="Project phase loading"
        className="inline-flex h-5 w-20 animate-pulse rounded-full bg-muted"
      />
    );
  }

  const phase = data.phase;
  const styleClass = isKnownPhase(phase) ? PHASE_STYLES[phase] : FALLBACK_STYLE;
  const log = data.phase_log ?? [];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Project phase: ${phase}. Click for transition history.`}
          data-phase={phase}
          className={cn(
            "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold capitalize transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
            styleClass,
          )}
        >
          {phase}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        <div className="text-sm font-semibold">Phase transitions</div>
        {log.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No transitions recorded yet.</p>
        ) : (
          <ul className="mt-2 space-y-1.5 text-sm">
            {log.map((entry) => (
              <PhaseLogRow key={`${entry.at}-${entry.from}-${entry.to}`} entry={entry} />
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}

function PhaseLogRow({ entry }: { entry: PhaseLogEntry }) {
  return (
    <li className="text-muted-foreground">
      <span className="font-medium text-foreground">
        {entry.from} → {entry.to}
      </span>
      <span className="ml-1">
        at {formatTimestamp(entry.at)}
        {entry.by ? ` by ${entry.by}` : ""}
      </span>
    </li>
  );
}

function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
