"use client"

import { Popover } from "@base-ui/react/popover"
import { Activity } from "lucide-react"
import { SystemPanel } from "@/components/layout/system-panel"
import { useIsOffline } from "@/lib/network/use-connectivity"
import { cn } from "@/lib/utils"
import { useStreamStatus } from "@/lib/websocket/use-stream"

type Tone = "ok" | "warn" | "idle"

const DOT: Record<Tone, string> = {
  ok: "bg-success",
  warn: "bg-warning",
  idle: "bg-muted-foreground/50",
}
const PILL: Record<Tone, string> = {
  ok: "border-success/30 text-success",
  warn: "border-warning/40 text-warning",
  idle: "border-border text-muted-foreground",
}

const TRIGGER_CLASS =
  "flex shrink-0 items-center gap-2 rounded-full border px-2.5 py-1 text-xs outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring data-[popup-open]:bg-accent"

const POPUP_CLASS =
  "z-50 w-80 origin-[var(--transform-origin)] overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-lg outline-none"

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
    <Popover.Root>
      <Popover.Trigger
        className={cn(TRIGGER_CLASS, PILL[tone])}
        aria-label={`system status, ${label}`}
      >
        <Activity aria-hidden="true" className="size-3.5 shrink-0" />
        <span aria-hidden="true" className="relative flex size-1.5 shrink-0">
          {tone === "ok" ? (
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-75 motion-reduce:hidden" />
          ) : null}
          <span
            className={cn(
              "relative inline-flex size-full rounded-full",
              DOT[tone],
              tone === "warn" && "animate-pulse motion-reduce:animate-none",
            )}
          />
        </span>
        {label}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="bottom" align="end" sideOffset={8}>
          <Popover.Popup className={POPUP_CLASS}>
            <SystemPanel />
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}
