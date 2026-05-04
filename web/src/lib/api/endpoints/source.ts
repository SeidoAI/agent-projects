import { useQuery } from "@tanstack/react-query";

import { apiGet, apiPost } from "../client";

export interface SourceFile {
  path: string;
  name: string;
  extension: string;
  size: number;
  content: string;
}

export const sourceApi = {
  get: (path: string) =>
    apiGet<SourceFile>(
      `/api/source?path=${encodeURIComponent(path)}`,
    ),
  open: (path: string) =>
    apiPost<{ opened: string }>(`/api/source/open`, { path }),
};

export function useSourceFile(path: string | null | undefined) {
  return useQuery<SourceFile>({
    queryKey: ["source", path],
    queryFn: () => sourceApi.get(path as string),
    enabled: Boolean(path),
    staleTime: 30_000,
    retry: false,
  });
}
