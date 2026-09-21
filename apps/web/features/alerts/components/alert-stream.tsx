"use client"
import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useState } from "react"
import { StreamIndicator } from "@/features/alerts/components/stream-indicator"
import { statsQueryKey } from "@/features/analytics/api/stats-key"
import type { StreamEnvelope } from "@/lib/websocket/envelope"
import { useStream } from "@/lib/websocket/use-stream"

export function AlertStream() {
  const queryClient = useQueryClient()
  const [lastEvent, setLastEvent] = useState<string | null>(null)
  const onEvent = useCallback(
    (envelope: StreamEnvelope) => {
      setLastEvent(envelope.event)
      void queryClient.invalidateQueries({ queryKey: statsQueryKey })
    },
    [queryClient],
  )
  useStream("alerts", onEvent)
  return (
    <div className="flex items-center justify-between gap-4">
      <StreamIndicator />
      {lastEvent === null ? null : (
        <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">
          last event {lastEvent}
        </span>
      )}
    </div>
  )
}
