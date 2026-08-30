"use client"

import { useQuery } from "@tanstack/react-query"
import { alertKeys, EMPTY_FILTERS } from "@/features/alerts/api/alert-keys"
import { fetchAlertPageClient } from "@/features/alerts/api/alerts-client"

const REFETCH_MS = 30_000

export function useCameraAlertCount(cameraId: string): number | null {
  const filters = { ...EMPTY_FILTERS, camera: cameraId }
  const { data } = useQuery({
    queryKey: alertKeys.list(filters),
    queryFn: ({ signal }) => fetchAlertPageClient(filters, null, signal),
    refetchInterval: REFETCH_MS,
  })
  return data === undefined ? null : data.items.length
}
