import { createBrowserRouter } from "react-router-dom";

import { StandaloneArtifactViewer } from "@/features/artifacts/StandaloneArtifactViewer";
import { ProjectDashboard } from "@/features/dashboard/ProjectDashboard";
import { ConceptGraph } from "@/features/graph/ConceptGraph";
import { IssueDetail } from "@/features/issues/IssueDetail";
import { KanbanBoard } from "@/features/issues/KanbanBoard";
import { NodeDetail } from "@/features/nodes/NodeDetail";
import { SessionDetail } from "@/features/sessions/SessionDetail";
import { SessionList } from "@/features/sessions/SessionList";
import { Placeholder } from "./Placeholder";
import { ProjectShell } from "./ProjectShell";
import { RootRedirect } from "./RootRedirect";

export const router = createBrowserRouter([
  { path: "/", element: <RootRedirect /> },
  { path: "/projects", element: <Placeholder name="ProjectList" /> },
  {
    path: "/p/:projectId",
    element: <ProjectShell />,
    children: [
      { index: true, element: <ProjectDashboard /> },
      { path: "board", element: <KanbanBoard /> },
      { path: "graph", element: <ConceptGraph /> },
      { path: "issues/:key", element: <IssueDetail /> },
      { path: "nodes/:nodeId", element: <NodeDetail /> },
      { path: "sessions", element: <SessionList /> },
      { path: "sessions/:sid", element: <SessionDetail /> },
      {
        path: "sessions/:sid/artifacts/:name",
        element: <StandaloneArtifactViewer />,
      },
      // Strand Z new screens — placeholders here in S1; S5/S6/S7 wire
      // the real implementations in. The ScreenShell nav already links
      // to these paths, so the routes must exist.
      { path: "workflow", element: <Placeholder name="WorkflowMap" /> },
      { path: "tripwires", element: <Placeholder name="TripwireLog" /> },
      { path: "sessions/:sid/live", element: <Placeholder name="LiveMonitor" /> },
    ],
  },
]);
