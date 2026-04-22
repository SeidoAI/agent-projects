import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useProjectShell } from "@/app/ProjectShell";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { queryKeys } from "@/lib/api/queryKeys";
import type { ValidationStatusData } from "@/lib/realtime/events";
import { cn } from "@/lib/utils";

/**
 * Validation indicator for the top bar. Reads `validationStatus(pid)` from
 * the TanStack cache — the only writer is the WebSocket handler on
 * `validation_completed` (see `eventHandlers.ts`). Absent data renders
 * as "Not validated yet."
 */
export function ValidationStatus() {
  const { projectId } = useProjectShell();
  const navigate = useNavigate();
  const { data } = useQuery<ValidationStatusData | null>({
    queryKey: queryKeys.validationStatus(projectId),
    // The backend has no GET endpoint for validation status in v1; the
    // WebSocket handler populates this key via setQueryData. Resolving
    // to null keeps the query quiescent until the first event arrives.
    queryFn: () => Promise.resolve(null),
    staleTime: Number.POSITIVE_INFINITY,
  });

  const variant = resolveVariant(data);
  const label = describe(variant, data);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={label}
          onClick={() => navigate(`/p/${projectId}/validation`)}
          className="inline-flex items-center gap-1.5 rounded text-sm text-muted-foreground hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
        >
          {variant === "clean" ? (
            <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">
              <Check aria-hidden className="h-3 w-3" />
            </span>
          ) : (
            <span
              aria-hidden
              className={cn(
                "h-2 w-2 rounded-full",
                variant === "errors" && "bg-red-500",
                variant === "never" && "bg-muted-foreground/40",
              )}
            />
          )}
          {variant === "errors" && data ? (
            <span className="font-medium text-red-600 dark:text-red-400">{data.errors}</span>
          ) : null}
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

type Variant = "never" | "clean" | "errors";

function resolveVariant(data: ValidationStatusData | null | undefined): Variant {
  if (!data) return "never";
  return data.errors > 0 ? "errors" : "clean";
}

function describe(variant: Variant, data: ValidationStatusData | null | undefined): string {
  switch (variant) {
    case "clean":
      return "Validation clean";
    case "errors": {
      const count = data?.errors ?? 0;
      return `${count} validation error${count === 1 ? "" : "s"} — open issue board to see`;
    }
    case "never":
      return "Not validated yet";
  }
}
