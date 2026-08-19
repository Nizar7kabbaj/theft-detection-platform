"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { FreshnessRing } from "@/features/cameras/components/freshness-ring"
import { useCameraFrames } from "@/features/cameras/hooks/use-camera-frames"
import {
  HEALTH_DETAIL,
  HEALTH_DOT,
  HEALTH_TEXT,
  useElapsedSeconds,
} from "@/features/cameras/lib/health"
import { HEALTH_STATE_VALUES, type HealthState } from "@/features/cameras/schemas/camera"

const STATUS_NOTICE: Record<string, string> = {
  connecting: "connecting",
  waiting: "reconnecting",
  stopped: "stream unavailable",
}

function toHealthState(value: string | null): HealthState {
  const match = HEALTH_STATE_VALUES.find((candidate) => candidate === value)
  return match ?? "unknown"
}

export function LiveView({
  cameraId,
  cameraName,
  lastFrameAt,
}: {
  cameraId: string
  cameraName: string
  lastFrameAt: string | null
}) {
  const { src, status, health } = useCameraFrames(cameraId)
  const [receivedAt, setReceivedAt] = useState<string | null>(lastFrameAt)
  const surface = useRef<HTMLDivElement>(null)
  const state = toHealthState(health)
  const notice = status === "open" ? "" : (STATUS_NOTICE[status] ?? "")
  const seconds = useElapsedSeconds(receivedAt)

  useEffect(() => {
    if (src !== null) {
      setReceivedAt(new Date().toISOString())
    }
  }, [src])

  const enterFullscreen = useCallback(() => {
    const node = surface.current
    if (node === null) {
      return
    }
    if (document.fullscreenElement === node) {
      void document.exitFullscreen()
      return
    }
    void node.requestFullscreen()
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <div
        ref={surface}
        className="relative aspect-video overflow-hidden rounded-xl bg-black ring-1 ring-foreground/10"
      >
        {src === null ? (
          <div className="absolute inset-0 flex items-center justify-center text-muted-foreground text-sm">
            {notice === "" ? "waiting for frames" : notice}
          </div>
        ) : (
          <img
            src={src}
            alt={`current frame from ${cameraName}`}
            className="h-full w-full object-contain"
          />
        )}
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 bg-gradient-to-b from-black/60 to-transparent p-3">
          <span className="flex items-center gap-2 rounded-md bg-black/50 px-2 py-1 text-xs text-white backdrop-blur-sm">
            <span
              aria-hidden="true"
              className={`size-2 rounded-full ${HEALTH_DOT[state]} ${
                state === "online" ? "animate-pulse" : ""
              }`}
            />
            {HEALTH_DETAIL[state]}
          </span>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={enterFullscreen}
            className="pointer-events-auto"
          >
            fullscreen
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <FreshnessRing state={state} seconds={seconds} />
        <div className="flex flex-col items-end gap-1 text-sm">
          <span className={HEALTH_TEXT[state]}>{HEALTH_DETAIL[state]}</span>
          {notice === "" ? null : <span className="text-muted-foreground">{notice}</span>}
          <span className="text-muted-foreground text-xs">frame shown unmirrored</span>
        </div>
      </div>
    </div>
  )
}
