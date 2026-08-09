"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import dynamic from "next/dynamic"
import { useState } from "react"
import { DEFAULT_GC_MS, DEFAULT_RETRY_COUNT, DEFAULT_STALE_MS } from "@/lib/api/query-config"

const DevtoolsPanel =
  process.env.NODE_ENV === "production"
    ? () => null
    : dynamic(
        () => import("@tanstack/react-query-devtools").then((mod) => mod.ReactQueryDevtools),
        { ssr: false },
      )

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: DEFAULT_STALE_MS,
        gcTime: DEFAULT_GC_MS,
        retry: DEFAULT_RETRY_COUNT,
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
      },
      mutations: {
        retry: 0,
      },
    },
  })
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(createQueryClient)

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <DevtoolsPanel />
    </QueryClientProvider>
  )
}
