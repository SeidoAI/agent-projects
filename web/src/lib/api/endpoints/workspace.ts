import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../client";
import { queryKeys, staleTime } from "../queryKeys";

export interface WorkspaceSummary {
  id: string;
  name: string;
  slug: string;
  dir: string;
  description?: string;
  project_slugs: string[];
}

export const workspaceApi = {
  list: () => apiGet<WorkspaceSummary[]>("/api/workspaces"),
};

/** v0.10.0 — drives the project switcher's grouping by workspace. */
export function useWorkspaces() {
  return useQuery({
    queryKey: queryKeys.workspaces(),
    queryFn: workspaceApi.list,
    staleTime: staleTime.default,
  });
}
