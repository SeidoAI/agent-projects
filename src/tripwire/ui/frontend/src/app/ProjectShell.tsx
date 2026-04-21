import { createContext, useContext } from "react";
import { Navigate, Outlet, useParams } from "react-router-dom";
import {
  type UseProjectWebSocketStatus,
  useProjectWebSocket,
} from "@/lib/realtime/useProjectWebSocket";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

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
  if (!projectId) return <Navigate to="/projects" replace />;
  return <ProjectShellInner projectId={projectId} />;
}

function ProjectShellInner({ projectId }: { projectId: string }) {
  const { status } = useProjectWebSocket(projectId);

  return (
    <ProjectShellContext.Provider value={{ projectId, wsStatus: status }}>
      <div className="flex h-screen flex-col">
        <TopBar />
        <div className="flex min-h-0 flex-1">
          <Sidebar />
          <main className="flex-1 overflow-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </ProjectShellContext.Provider>
  );
}
