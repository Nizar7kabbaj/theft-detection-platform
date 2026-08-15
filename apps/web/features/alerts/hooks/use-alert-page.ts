"use client"
import { useInfiniteQuery } from "@tanstack/react-query"
import { type AlertFilters, alertKeys } from "@/features/alerts/api/alert-keys"
import { fetchAlertPageClient } from "@/features/alerts/api/alerts-client"
import type { AlertPage } from "@/features/alerts/schemas/alert"
import { ALERT_LIST_GC_MS, ALERT_LIST_STALE_MS } from "@/lib/api/query-config"

export function useAlertPage(filters: AlertFilters) {
  return useInfiniteQuery<AlertPage>({
    queryKey: alertKeys.list(filters),
    queryFn: ({ pageParam, signal }) =>
      fetchAlertPageClient(filters, pageParam as string | null, signal),
    initialPageParam: null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: ALERT_LIST_STALE_MS,
    gcTime: ALERT_LIST_GC_MS,
    refetchOnWindowFocus: false,
  })
}
