import { createContext, useContext } from "react";
import { Navigate, Outlet, useParams } from "react-router-dom";
import { TweaksProvider } from "@/components/tweaks/TweaksContext";
import { TweaksPanel } from "@/components/tweaks/TweaksPanel";
import { ScreenShell } from "@/components/ui/screen-shell";
import {
  type UseProjectWebSocketStatus,
  useProjectWebSocket,
} from "@/lib/realtime/useProjectWebSocket";
import { ProjectStatusCluster } from "./ProjectStatusCluster";

interface ProjectShellContextValue {
  projectId: string;
  wsStatus: UseProjectWebSocketStatus;
}

const ProjectShellContext = createContext<ProjectShellContextValue | null>(null);

export function useProjectShell(): ProjectShellContextValue {
  const ctx = useContext(ProjectShellContext);
  if (!ctx) throw new Error("useProjectShell must be used within ProjectShell");
  return ctx;
}

export function ProjectShell() {
  const { projectId } = useParams();
  if (!projectId) return <Navigate to="/" replace />;
  return <ProjectShellInner projectId={projectId} />;
}

function ProjectShellInner({ projectId }: { projectId: string }) {
  const { status } = useProjectWebSocket(projectId);

  return (
    <ProjectShellContext.Provider value={{ projectId, wsStatus: status }}>
      <TweaksProvider>
        <ScreenShell
          projectId={projectId}
          topBarStatus={<ProjectStatusCluster wsStatus={status} />}
        >
          <Outlet />
        </ScreenShell>
        <TweaksPanel />
      </TweaksProvider>
    </ProjectShellContext.Provider>
  );
}
