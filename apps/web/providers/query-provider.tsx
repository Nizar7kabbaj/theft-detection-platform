"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import dynamic from "next/dynamic"
import { useEffect, useState } from "react"
import { setSessionFailureHandler } from "@/lib/api/client"
import { isRetryable } from "@/lib/api/errors"
import {
  DEFAULT_GC_MS,
  DEFAULT_STALE_MS,
  MAX_RETRY_COUNT,
  RETRY_BASE_DELAY_MS,
  RETRY_MAX_DELAY_MS,
} from "@/lib/api/query-config"

const DevtoolsPanel =
  process.env.NODE_ENV === "production"
    ? () => null
    : dynamic(
        () => import("@tanstack/react-query-devtools").then((mod) => mod.ReactQueryDevtools),
        { ssr: false },
      )

function shouldRetry(failureCount: number, error: Error): boolean {
  return failureCount < MAX_RETRY_COUNT && isRetryable(error)
}

function retryDelay(attemptIndex: number): number {
  return Math.min(RETRY_BASE_DELAY_MS * 2 ** attemptIndex, RETRY_MAX_DELAY_MS)
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: DEFAULT_STALE_MS,
        gcTime: DEFAULT_GC_MS,
        retry: shouldRetry,
        retryDelay,
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

  useEffect(() => {
    setSessionFailureHandler(() => {
      queryClient.cancelQueries()
      queryClient.clear()
    })
    return () => setSessionFailureHandler(null)
  }, [queryClient])

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <DevtoolsPanel />
    </QueryClientProvider>
  )
}
