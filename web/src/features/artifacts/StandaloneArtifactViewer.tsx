import { Link, useParams } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { useSessionArtifacts } from "@/lib/api/endpoints/artifacts";
import { ArtifactViewer } from "./ArtifactViewer";

export function StandaloneArtifactViewer() {
  const { projectId, sid, name } = useParams<{
    projectId: string;
    sid: string;
    name: string;
  }>();
  if (!projectId || !sid || !name) {
    return <NotFound projectId={projectId} sid={sid} />;
  }
  return <StandaloneInner projectId={projectId} sid={sid} name={name} />;
}

function StandaloneInner({
  projectId,
  sid,
  name,
}: {
  projectId: string;
  sid: string;
  name: string;
}) {
  const { data: statuses } = useSessionArtifacts(projectId, sid);
  const status = statuses?.find((s) => s.spec.name === name);

  return (
    <TooltipProvider>
      <div className="flex flex-col gap-4 p-8">
        <div className="text-sm text-muted-foreground">
          <Link
            to={`/p/${projectId}/sessions/${sid}`}
            className="underline decoration-dotted hover:decoration-solid"
          >
            ← Back to session
          </Link>
        </div>
        <ArtifactViewer projectId={projectId} sessionId={sid} name={name} status={status} />
      </div>
    </TooltipProvider>
  );
}

function NotFound({ projectId, sid }: { projectId?: string; sid?: string }) {
  const sessionHref = projectId && sid ? `/p/${projectId}/sessions/${sid}` : "/";
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold">Artifact not found</h1>
      <Link to={sessionHref} className="mt-4 inline-block text-sm underline">
        ← Back
      </Link>
    </div>
  );
}
