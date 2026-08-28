"use client"

import { useStreamStatus } from "@/lib/websocket/use-stream"

const LABEL: Record<string, string> = {
  idle: "not connected",
  connecting: "connecting",
  open: "stream connected",
  waiting: "reconnecting",
  offline: "no network",
  stopped: "disconnected",
}

const DOT_CLASS: Record<string, string> = {
  idle: "bg-muted-foreground",
  connecting: "bg-warning",
  open: "bg-success",
  waiting: "bg-warning",
  offline: "bg-destructive",
  stopped: "bg-muted-foreground",
}

export function StreamIndicator() {
  const status = useStreamStatus("alerts")

  return (
    <span className="flex items-center gap-2">
      <span
        aria-hidden="true"
        className={`size-1.5 rounded-full ${DOT_CLASS[status] ?? "bg-muted-foreground"}`}
      />
      <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider">
        {LABEL[status] ?? status}
      </span>
    </span>
  )
}
