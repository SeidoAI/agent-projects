import { Navigate } from "react-router-dom";

export function RootRedirect() {
  // Smart redirect (auto-pick the only project) deferred to KUI-54.
  // For now, always redirect to the project list.
  return <Navigate to="/projects" replace />;
}
