"use client"
import { useIsOffline } from "@/lib/network/use-connectivity"
import { cn } from "@/lib/utils"
import { useStreamStatus } from "@/lib/websocket/use-stream"

type Tone = "ok" | "warn" | "idle"

const DOT: Record<Tone, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  idle: "bg-muted-foreground/50",
}

const PILL: Record<Tone, string> = {
  ok: "border-emerald-500/30 text-emerald-400",
  warn: "border-amber-500/40 text-amber-400",
  idle: "border-border text-muted-foreground",
}

export function SystemStatus() {
  const offline = useIsOffline()
  const status = useStreamStatus("alerts")
  let tone: Tone = "idle"
  let label = "no live feed"
  if (offline) {
    tone = "warn"
    label = "offline"
  } else if (status === "open") {
    tone = "ok"
    label = "live"
  } else if (status === "connecting" || status === "waiting") {
    tone = "warn"
    label = "reconnecting"
  } else if (status === "stopped" || status === "offline") {
    tone = "warn"
    label = "disconnected"
  }
  return (
    <span
      role="status"
      aria-live="polite"
      className={cn(
        "flex shrink-0 items-center gap-2 rounded-full border px-2.5 py-1 text-xs",
        PILL[tone],
      )}
    >
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", DOT[tone])} />
      {label}
    </span>
  )
}
