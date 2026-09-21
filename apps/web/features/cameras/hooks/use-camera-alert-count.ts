"use client"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"
import { EMPTY_FILTERS } from "@/features/alerts/api/alert-keys"
import { fetchAlertCountClient } from "@/features/alerts/api/alerts-client"
import type { StreamEnvelope } from "@/lib/websocket/envelope"
import { useStream } from "@/lib/websocket/use-stream"

const REFETCH_MS = 30_000
const COUNT_EVENTS = new Set(["created", "deleted"])

export function useCameraAlertCount(cameraId: string): number | null {
  const queryClient = useQueryClient()
  const filters = { ...EMPTY_FILTERS, camera: cameraId, range: "today" as const }
  const { data } = useQuery({
    queryKey: ["alerts", "count", cameraId, "today"],
    queryFn: ({ signal }) => fetchAlertCountClient(filters, signal),
    refetchInterval: REFETCH_MS,
  })
  const onEvent = useCallback(
    (envelope: StreamEnvelope) => {
      if (COUNT_EVENTS.has(envelope.event)) {
        void queryClient.invalidateQueries({ queryKey: ["alerts", "count", cameraId, "today"] })
      }
    },
    [queryClient, cameraId],
  )
  useStream("alerts", onEvent)
  return data === undefined ? null : data
}
