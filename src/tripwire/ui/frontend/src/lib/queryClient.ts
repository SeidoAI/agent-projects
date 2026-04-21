import { QueryClient } from "@tanstack/react-query";
import { staleTime } from "./api/queryKeys";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: staleTime.default,
      refetchOnWindowFocus: false,
      retry: 1,
    },
    mutations: {
      retry: 0,
    },
  },
});
