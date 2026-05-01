import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  type ArtifactStatus,
  useArtifactManifest,
  useSessionArtifacts,
} from "@/lib/api/endpoints/artifacts";
import { cn } from "@/lib/utils";
import { ArtifactViewer } from "./ArtifactViewer";

interface ArtifactListProps {
  projectId: string;
  sessionId: string;
  initialName?: string;
  onTabChange?: (name: string) => void;
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "missing";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diffMs = Date.now() - then;
  if (diffMs < 0) return "just now";
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function ArtifactList({
  projectId,
  sessionId,
  initialName,
  onTabChange,
}: ArtifactListProps) {
  const { data: manifest, isLoading: manifestLoading } = useArtifactManifest(projectId);
  const { data: statuses, isLoading: statusesLoading } = useSessionArtifacts(projectId, sessionId);

  if (manifestLoading || statusesLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const entries = manifest?.artifacts ?? [];
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No artifact manifest configured for this project.
      </p>
    );
  }

  const statusByName = new Map<string, ArtifactStatus>();
  for (const st of statuses ?? []) statusByName.set(st.spec.name, st);

  const firstEntry = entries[0];
  if (!firstEntry) return null;
  const defaultTab = initialName ?? firstEntry.name;

  return (
    <Tabs
      defaultValue={defaultTab}
      onValueChange={onTabChange}
      className="w-full"
      data-testid="artifact-tabs"
    >
      <TabsList className="flex h-auto flex-wrap justify-start gap-1 bg-transparent p-0">
        {entries.map((spec) => {
          const st = statusByName.get(spec.name);
          const present = st?.present ?? false;
          const approval = st?.approval;
          const rel = formatRelativeTime(st?.last_modified ?? null);
          const trigger = (
            <TabsTrigger
              key={spec.name}
              value={spec.name}
              className={cn(
                "flex items-center gap-1.5 border border-transparent data-[state=active]:border-border",
                !present && "opacity-60",
              )}
              data-tab-name={spec.name}
              data-present={present ? "true" : "false"}
            >
              <span
                role="img"
                aria-label={present ? "present" : "missing"}
                className={cn(
                  "h-2 w-2 rounded-full",
                  present ? "bg-emerald-500" : "bg-muted-foreground/50",
                )}
              />
              <span>{spec.name}</span>
              {approval ? (
                <span
                  className={cn("text-xs", approval.approved ? "text-emerald-500" : "text-red-500")}
                >
                  {approval.approved ? "✓" : "✗"}
                </span>
              ) : null}
              <span className="text-xs text-muted-foreground">{rel}</span>
            </TabsTrigger>
          );
          if (present) return trigger;
          return (
            <Tooltip key={spec.name}>
              <TooltipTrigger asChild>{trigger}</TooltipTrigger>
              <TooltipContent>
                Not yet produced. Expected at sessions/{sessionId}/{spec.file}.
              </TooltipContent>
            </Tooltip>
          );
        })}
      </TabsList>
      {entries.map((spec) => (
        <TabsContent key={spec.name} value={spec.name} className="mt-4">
          <ArtifactViewer
            projectId={projectId}
            sessionId={sessionId}
            name={spec.name}
            status={statusByName.get(spec.name)}
          />
        </TabsContent>
      ))}
    </Tabs>
  );
}
