import { createBrowserRouter, Navigate } from "react-router-dom";
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
      { index: true, element: <Navigate to="board" replace /> },
      { path: "board", element: <Placeholder name="KanbanBoard" /> },
      { path: "graph", element: <Placeholder name="ConceptGraph" /> },
      { path: "issues/:key", element: <Placeholder name="IssueDetail" /> },
      { path: "nodes/:nodeId", element: <Placeholder name="NodeDetail" /> },
      { path: "sessions", element: <Placeholder name="SessionList" /> },
      { path: "sessions/:sid", element: <Placeholder name="SessionDetail" /> },
      {
        path: "sessions/:sid/artifacts/:name",
        element: <Placeholder name="ArtifactViewer" />,
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
