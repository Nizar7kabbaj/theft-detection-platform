"use client"

import { FrameCanvas } from "@/features/cameras/components/frame-canvas"
import { FreshnessRing } from "@/features/cameras/components/freshness-ring"
import { useFrameBitmap } from "@/features/cameras/hooks/use-frame-bitmap"
import { useElapsedSeconds } from "@/features/cameras/lib/health"
import { HEALTH_STATE_VALUES, type HealthState } from "@/features/cameras/schemas/camera"

function toHealthState(value: string | null): HealthState {
  const match = HEALTH_STATE_VALUES.find((candidate) => candidate === value)
  return match ?? "unknown"
}

export function CameraPreview({
  cameraId,
  cameraName,
  lastFrameAt,
  registeredState,
  height,
}: {
  cameraId: string
  cameraName: string
  lastFrameAt: string | null
  registeredState: HealthState
  height?: string
}) {
  const { bitmapRef, status, health, stats } = useFrameBitmap(cameraId)
  const state = health === null ? registeredState : toHealthState(health)
  const seconds = useElapsedSeconds(stats.lastFrameAt ?? lastFrameAt)

  return (
    <div className="flex flex-col gap-3">
      <FrameCanvas
        bitmapRef={bitmapRef}
        cameraName={cameraName}
        health={health}
        height={height}
        pose={null}
        status={status}
        threshold={0.3}
      />
      <FreshnessRing seconds={seconds} state={state} />
    </div>
  )
}
