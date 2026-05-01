import { createBrowserRouter } from "react-router-dom";

import { StandaloneArtifactViewer } from "@/features/artifacts/StandaloneArtifactViewer";
import { Board } from "@/features/board/Board";
import { ProjectDashboard } from "@/features/dashboard/ProjectDashboard";
import { DriftReport } from "@/features/drift/DriftReport";
import { EventLog } from "@/features/events/EventLog";
import { ConceptGraph } from "@/features/graph/ConceptGraph";
import { IssueDetail } from "@/features/issues/IssueDetail";
import { LiveMonitor } from "@/features/live/LiveMonitor";
import { NodeDetail } from "@/features/nodes/NodeDetail";
import { ProcessQuality } from "@/features/process-quality/ProcessQuality";
import { SessionDetail } from "@/features/sessions/SessionDetail";
import { SessionList } from "@/features/sessions/SessionList";
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
      { path: "sessions", element: <SessionList /> },
      { path: "sessions/:sid", element: <SessionDetail /> },
      {
        path: "sessions/:sid/artifacts/:name",
        element: <StandaloneArtifactViewer />,
      },
      { path: "workflow", element: <WorkflowMap /> },
      { path: "events", element: <EventLog /> },
      { path: "process-quality", element: <ProcessQuality /> },
      { path: "drift", element: <DriftReport /> },
      { path: "sessions/:sid/live", element: <LiveMonitor /> },
    ],
  },
]);
