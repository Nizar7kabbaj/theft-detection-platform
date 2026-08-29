"use client"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { alertKeys } from "@/features/alerts/api/alert-keys"
import { acknowledgeAlert, fetchAlertDetailClient } from "@/features/alerts/api/alerts-client"
import type { AlertDetail } from "@/features/alerts/schemas/alert"
import { ALERT_DETAIL_GC_MS, ALERT_DETAIL_STALE_MS } from "@/lib/api/query-config"

export function useAlertDetail(id: string, initial: AlertDetail) {
  return useQuery({
    queryKey: alertKeys.detail(id),
    queryFn: ({ signal }) => fetchAlertDetailClient(id, signal),
    initialData: initial,
    staleTime: ALERT_DETAIL_STALE_MS,
    gcTime: ALERT_DETAIL_GC_MS,
  })
}

export function useAcknowledgeDetail(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => acknowledgeAlert(id),
    onSuccess: (updated) => {
      queryClient.setQueryData<AlertDetail>(alertKeys.detail(id), (current) => {
        if (current === undefined) {
          return current
        }
        return {
          ...current,
          acknowledged: updated.acknowledged,
          acknowledged_at: updated.acknowledged_at,
        }
      })
      void queryClient.invalidateQueries({ queryKey: alertKeys.all })
    },
  })
}
