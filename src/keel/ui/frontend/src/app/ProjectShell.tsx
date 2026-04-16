import { createContext, useContext } from "react";
import { Navigate, Outlet, useParams } from "react-router-dom";
import { AgentStatusBar } from "./AgentStatusBar";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

interface ProjectShellContextValue {
  projectId: string;
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

  return (
    <ProjectShellContext.Provider value={{ projectId }}>
      <div className="flex h-screen flex-col">
        <TopBar />
        <div className="flex min-h-0 flex-1">
          <Sidebar />
          <main className="flex-1 overflow-auto">
            <Outlet />
          </main>
        </div>
        <AgentStatusBar />
      </div>
    </ProjectShellContext.Provider>
  );
}
