"use client"

import { Video } from "lucide-react"
import { type Camera, cameraHealth, type HealthState } from "@/features/cameras/schemas/camera"

const STATE_DOT: Record<HealthState, string> = {
  online: "bg-success",
  degraded: "bg-warning",
  offline: "bg-destructive",
  unknown: "bg-muted-foreground/50",
}

const STATE_TEXT: Record<HealthState, string> = {
  online: "text-success",
  degraded: "text-warning",
  offline: "text-destructive",
  unknown: "text-muted-foreground",
}

function frameAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return "--"
  }
  const whole = Math.max(0, Math.round(seconds))
  if (whole < 60) {
    return `${whole}s`
  }
  const minutes = Math.floor(whole / 60)
  if (minutes < 60) {
    return `${minutes}m`
  }
  return `${Math.floor(minutes / 60)}h`
}

function Cell({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="font-mono text-[9px] text-muted-foreground uppercase">{label}</span>
      <span className={`truncate font-mono text-xs tabular-nums ${tone ?? ""}`}>{value}</span>
    </div>
  )
}

export function FleetTile({
  camera,
  selected,
  onSelect,
}: {
  camera: Camera
  selected: boolean
  onSelect: (cameraId: string) => void
}) {
  const health = cameraHealth(camera)
  const state = health.state

  return (
    <button
      aria-pressed={selected}
      className={`flex w-full flex-col gap-3 rounded-lg border p-3.5 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring ${
        selected
          ? "border-foreground/25 bg-secondary"
          : "border-border bg-card hover:border-foreground/20 hover:bg-secondary/40"
      }`}
      onClick={() => onSelect(camera.camera_id)}
      type="button"
    >
      <div className="flex items-start gap-2.5">
        <span
          aria-hidden="true"
          className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-secondary/60"
        >
          <Video className="size-3.5 text-muted-foreground" />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate font-semibold text-sm tracking-tight">{camera.name}</span>
          <span className="truncate font-mono text-[10px] text-muted-foreground uppercase">
            {camera.camera_id}
            {camera.location === "" ? "" : ` · ${camera.location}`}
          </span>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm border border-border px-1.5 py-0.5 font-mono text-[9px] uppercase ${STATE_TEXT[state]}`}
        >
          <span
            aria-hidden="true"
            className={`size-1.5 rounded-full ${STATE_DOT[state]} ${
              state === "online" ? "animate-pulse" : ""
            }`}
          />
          {state}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 border-border/60 border-t pt-3">
        <Cell label="last frame" value={frameAge(health.age_seconds)} />
        <Cell label="status" value={camera.status} />
        <Cell label="registered" value={camera.created_at.slice(0, 10)} />
      </div>
    </button>
  )
}
