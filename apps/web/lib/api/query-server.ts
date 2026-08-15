import { QueryClient } from "@tanstack/react-query"
import { DEFAULT_GC_MS, DEFAULT_STALE_MS } from "@/lib/api/query-config"
import "server-only"

export function createServerQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: DEFAULT_STALE_MS,
        gcTime: DEFAULT_GC_MS,
        retry: false,
      },
    },
  })
}
