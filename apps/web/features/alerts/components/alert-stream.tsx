"use client"
import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useState } from "react"
import { statsQueryKey } from "@/features/analytics/api/stats-key"
import type { StreamEnvelope } from "@/lib/websocket/envelope"
import { useStream, useStreamRetry, useStreamStatus } from "@/lib/websocket/use-stream"

const LABEL: Record<string, string> = {
  idle: "not connected",
  connecting: "connecting",
  open: "live",
  waiting: "reconnecting",
  stopped: "disconnected",
}

export function AlertStream() {
  const queryClient = useQueryClient()
  const [lastEvent, setLastEvent] = useState<string | null>(null)
  const status = useStreamStatus("alerts")
  const retry = useStreamRetry("alerts")

  const onEvent = useCallback(
    (envelope: StreamEnvelope) => {
      setLastEvent(envelope.event)
      void queryClient.invalidateQueries({ queryKey: statsQueryKey })
    },
    [queryClient],
  )

  useStream("alerts", onEvent)

  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-muted-foreground">
        {LABEL[status] ?? status}
        {lastEvent === null ? "" : ` · last event ${lastEvent}`}
      </span>
      {status === "stopped" ? (
        <button
          type="button"
          onClick={retry}
          className="rounded border px-2 py-1 text-xs hover:bg-muted"
        >
          reconnect
        </button>
      ) : null}
    </div>
  )
}
