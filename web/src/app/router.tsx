import { createBrowserRouter } from "react-router-dom";

import { StandaloneArtifactViewer } from "@/features/artifacts/StandaloneArtifactViewer";
import { Board } from "@/features/board/Board";
import { ProjectDashboard } from "@/features/dashboard/ProjectDashboard";
import { ConceptGraph } from "@/features/graph/ConceptGraph";
import { IssueDetail } from "@/features/issues/IssueDetail";
import { LiveMonitor } from "@/features/live/LiveMonitor";
import { Monitor } from "@/features/monitor/Monitor";
import { NodeDetail } from "@/features/nodes/NodeDetail";
import { Quality } from "@/features/quality/Quality";
import { SessionDetail } from "@/features/sessions/SessionDetail";
import { WorkflowMap } from "@/features/workflow/WorkflowMap";
import { ProjectShell } from "./ProjectShell";
import { RootRedirect } from "./RootRedirect";

export const router = createBrowserRouter([
  { path: "/", element: <RootRedirect /> },
  {
    path: "/p/:projectId",
    element: <ProjectShell />,
    children: [
      { index: true, element: <ProjectDashboard /> },
      { path: "board", element: <Board /> },
      { path: "graph", element: <ConceptGraph /> },
      { path: "issues/:key", element: <IssueDetail /> },
      { path: "nodes/:nodeId", element: <NodeDetail /> },
      { path: "sessions/:sid", element: <SessionDetail /> },
      {
        path: "sessions/:sid/artifacts/:name",
        element: <StandaloneArtifactViewer />,
      },
      { path: "workflow", element: <WorkflowMap /> },
      { path: "quality", element: <Quality /> },
      { path: "monitor", element: <Monitor /> },
      { path: "sessions/:sid/live", element: <LiveMonitor /> },
    ],
  },
]);
