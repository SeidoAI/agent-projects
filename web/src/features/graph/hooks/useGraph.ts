import { useQuery } from "@tanstack/react-query";

import { graphApi } from "@/lib/api/endpoints/graph";
import { queryKeys, staleTime } from "@/lib/api/queryKeys";

export function useConceptGraph(pid: string) {
  return useQuery({
    queryKey: queryKeys.graph(pid, "concept"),
    queryFn: () => graphApi.concept(pid),
    staleTime: staleTime.default,
  });
}
