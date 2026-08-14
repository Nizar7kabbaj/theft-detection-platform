"use client"
import { useCallback, useState } from "react"
import { recheckReachability, useIsOffline } from "@/lib/network/use-connectivity"
import { useStreamRetry, useStreamStatus } from "@/lib/websocket/use-stream"

type Banner = {
  tone: "warn" | "info"
  message: string
  action: string | null
}

export function ConnectionBanner() {
  const offline = useIsOffline()
  const status = useStreamStatus("alerts")
  const retryStream = useStreamRetry("alerts")
  const [checking, setChecking] = useState(false)

  const onCheck = useCallback(async () => {
    setChecking(true)
    try {
      await recheckReachability()
    } finally {
      setChecking(false)
    }
  }, [])

  let banner: Banner | null = null
  if (offline) {
    banner = { tone: "warn", message: "no network connection", action: "check again" }
  } else if (status === "stopped") {
    banner = { tone: "warn", message: "live updates disconnected", action: "reconnect" }
  } else if (status === "waiting" || status === "connecting") {
    banner = { tone: "info", message: "reconnecting to live updates", action: null }
  }

  if (banner === null) {
    return null
  }

  const onAction = offline ? onCheck : retryStream
  const disabled = offline && checking

  return (
    <div
      role="status"
      aria-live="polite"
      className={
        banner.tone === "warn"
          ? "flex items-center justify-between gap-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm"
          : "flex items-center justify-between gap-4 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm"
      }
    >
      <span className="text-muted-foreground">{banner.message}</span>
      {banner.action === null ? null : (
        <button
          type="button"
          onClick={onAction}
          disabled={disabled}
          className="rounded border px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
        >
          {disabled ? "checking" : banner.action}
        </button>
      )}
    </div>
  )
}
