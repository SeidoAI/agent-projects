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
import { V2Placeholder } from "./V2Placeholder";

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
      { path: "orchestration", element: <Placeholder name="OrchestrationView" /> },

      // v2 placeholders
      { path: "agents", element: <V2Placeholder feature="Agents" /> },
      { path: "agents/:sessionId", element: <V2Placeholder feature="Agent session detail" /> },
      { path: "messages", element: <V2Placeholder feature="Messages" /> },
      { path: "messages/:sessionId", element: <V2Placeholder feature="Message thread" /> },
      { path: "approvals", element: <V2Placeholder feature="Approval queue" /> },
      { path: "pm-reviews", element: <V2Placeholder feature="PM reviews" /> },
    ],
  },
]);
