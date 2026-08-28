"use client"

import { type InfiniteData, useMutation, useQueryClient } from "@tanstack/react-query"
import { type AlertFilters, alertKeys } from "@/features/alerts/api/alert-keys"
import { acknowledgeAlert } from "@/features/alerts/api/alerts-client"
import type { AlertPage } from "@/features/alerts/schemas/alert"

export function useAcknowledgeAlert(id: string, filters: AlertFilters) {
  const queryClient = useQueryClient()
  const key = alertKeys.list(filters)

  return useMutation({
    mutationFn: () => acknowledgeAlert(id),
    onSuccess: (updated) => {
      queryClient.setQueryData<InfiniteData<AlertPage, string | null>>(key, (current) => {
        if (current === undefined) {
          return current
        }
        return {
          ...current,
          pages: current.pages.map((page) => ({
            ...page,
            items: page.items.map((item) => (item._id === updated._id ? updated : item)),
          })),
        }
      })
    },
  })
}
