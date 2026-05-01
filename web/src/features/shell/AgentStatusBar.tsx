import { ChevronRight, Users } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const V2_MESSAGE = "Agent monitoring ships in v2 — requires session-runtime telemetry";

// v2: render one card per running session.
export function AgentStatusBar() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          role="status"
          aria-label={V2_MESSAGE}
          title={V2_MESSAGE}
          className="pointer-events-auto inline-flex items-center gap-1.5 text-xs text-muted-foreground/80"
        >
          <Users aria-hidden className="h-3.5 w-3.5" />
          <span>0 agents running</span>
          <ChevronRight aria-hidden className="h-3.5 w-3.5 opacity-50" />
        </div>
      </TooltipTrigger>
      <TooltipContent>{V2_MESSAGE}</TooltipContent>
    </Tooltip>
  );
}
