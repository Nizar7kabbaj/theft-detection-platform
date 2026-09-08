"use client"
import { useQuery } from "@tanstack/react-query"
import { EMPTY_FILTERS } from "@/features/alerts/api/alert-keys"
import { fetchAlertCountClient } from "@/features/alerts/api/alerts-client"

const REFETCH_MS = 30_000
export function useCameraAlertCount(cameraId: string): number | null {
  const filters = { ...EMPTY_FILTERS, camera: cameraId, range: "today" as const }
  const { data } = useQuery({
    queryKey: ["alerts", "count", cameraId, "today"],
    queryFn: ({ signal }) => fetchAlertCountClient(filters, signal),
    refetchInterval: REFETCH_MS,
  })
  return data === undefined ? null : data
}
