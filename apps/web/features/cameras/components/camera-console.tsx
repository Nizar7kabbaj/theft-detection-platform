"use client"

import { Video } from "lucide-react"
import type { Route } from "next"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback } from "react"
import { EmptyState } from "@/components/ui/empty-state"
import {
  CAMERA_COOKIE_MAX_AGE,
  CAMERA_COOKIE_NAME,
  type FleetFilter,
  parseCameraId,
} from "@/features/cameras/api/camera-cookie"
import { CameraDetail } from "@/features/cameras/components/camera-detail"
import { FleetColumn } from "@/features/cameras/components/fleet-column"
import { FrameCanvas } from "@/features/cameras/components/frame-canvas"
import { FreshnessRing } from "@/features/cameras/components/freshness-ring"
import { useCameraGrid } from "@/features/cameras/hooks/use-camera-grid"
import { useFrameBitmap } from "@/features/cameras/hooks/use-frame-bitmap"
import { useElapsedSeconds } from "@/features/cameras/lib/health"
import {
  type Camera,
  cameraHealth,
  HEALTH_STATE_VALUES,
  type HealthState,
} from "@/features/cameras/schemas/camera"
import { writeCookie } from "@/lib/cookies/write"

const SKELETON_KEYS = ["a", "b", "c"] as const
const ABSENT = "not on this stream"

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

function toHealthState(value: string | null): HealthState {
  const match = HEALTH_STATE_VALUES.find((candidate) => candidate === value)
  return match ?? "unknown"
}

function Reading({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 border-border border-r px-3.5 py-3 last:border-r-0">
      <span className="font-mono text-[9px] text-muted-foreground uppercase">{label}</span>
      <span className="font-mono text-sm tabular-nums">{value}</span>
      <span className="truncate font-mono text-[9px] text-muted-foreground">{note}</span>
    </div>
  )
}

function ConsoleBody({
  cameras,
  initialCameraId,
  initialFilter,
}: {
  cameras: Camera[]
  initialCameraId: string | null
  initialFilter: FleetFilter
}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const fromUrl = parseCameraId(searchParams.get("id"))
  const wanted = fromUrl ?? initialCameraId
  const first = cameras[0]
  const selected = cameras.find((camera) => camera.camera_id === wanted) ?? first

  const select = useCallback(
    (cameraId: string) => {
      writeCookie(CAMERA_COOKIE_NAME, cameraId, CAMERA_COOKIE_MAX_AGE)
      const next = new URLSearchParams(searchParams.toString())
      next.set("id", cameraId)
      router.replace(`${pathname}?${next.toString()}` as Route, { scroll: false })
    },
    [pathname, router, searchParams],
  )

  if (selected === undefined) {
    return null
  }

  return (
    <ConsoleView
      camera={selected}
      cameras={cameras}
      initialFilter={initialFilter}
      onSelect={select}
    />
  )
}

function ConsoleView({
  camera,
  cameras,
  onSelect,
  initialFilter,
}: {
  camera: Camera
  cameras: Camera[]
  onSelect: (cameraId: string) => void
  initialFilter: FleetFilter
}) {
  const { bitmapRef, status, health, stats } = useFrameBitmap(camera.camera_id)
  const registered = cameraHealth(camera)
  const state = health === null ? registered.state : toHealthState(health)
  const seconds = useElapsedSeconds(stats.lastFrameAt ?? registered.last_frame_at ?? null)

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="grid grid-cols-2 rounded-lg border border-border bg-card sm:grid-cols-3 lg:grid-cols-6">
        <Reading
          label="frames"
          note="this session"
          value={stats.frames === 0 ? "--" : String(stats.frames)}
        />
        <Reading
          label="fps"
          note="measured at viewer"
          value={stats.fps === null || stats.frames === 0 ? "--" : `${stats.fps} fps`}
        />
        <Reading label="persons" note={ABSENT} value="--" />
        <Reading label="inference" note={ABSENT} value="--" />
        <Reading label="resolution" note={ABSENT} value="--" />
        <Reading label="alerts" note="not wired yet" value="--" />
      </div>
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-card p-3.5">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="flex min-w-0 flex-col gap-0.5">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <h2 className="font-semibold text-sm tracking-tight">{camera.name}</h2>
                <span className="font-mono text-[10px] text-muted-foreground uppercase">
                  {camera.camera_id} · selected source
                </span>
              </div>
              <span className="truncate text-muted-foreground text-xs">
                {camera.location === "" ? "no location recorded" : camera.location}
              </span>
            </div>
            <span
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm border border-border px-1.5 py-0.5 font-mono text-[9px] uppercase ${STATE_TEXT[state]}`}
            >
              <span aria-hidden="true" className={`size-1.5 rounded-full ${STATE_DOT[state]}`} />
              {state}
            </span>
          </div>
          <FrameCanvas
            bitmapRef={bitmapRef}
            cameraName={camera.name}
            health={health}
            pose={null}
            status={status}
            threshold={0.3}
          />
          <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-4 border-border border-t pt-3">
            <FreshnessRing seconds={seconds} state={state} />
            <CameraDetail camera={camera} />
          </div>
        </div>
        <FleetColumn
          cameras={cameras}
          initialFilter={initialFilter}
          onSelect={onSelect}
          selectedId={camera.camera_id}
        />
      </div>
    </div>
  )
}

export function CameraConsole({
  initialCameraId,
  initialFilter,
}: {
  initialCameraId: string | null
  initialFilter: FleetFilter
}) {
  const { cameras, isPending, isError } = useCameraGrid()

  if (isError) {
    return (
      <EmptyState
        description="the camera list could not be loaded. check the connection and retry."
        icon={Video}
        title="cameras unavailable"
      />
    )
  }

  if (isPending) {
    return (
      <div aria-busy="true" className="flex flex-col gap-4">
        <div className="h-20 animate-pulse rounded-lg bg-muted/40" />
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="aspect-video animate-pulse rounded-lg bg-muted/40" />
          <div className="flex flex-col gap-2">
            {SKELETON_KEYS.map((placeholder) => (
              <div className="h-24 animate-pulse rounded-lg bg-muted/40" key={placeholder} />
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (cameras.length === 0) {
    return (
      <EmptyState
        description="capture sources appear here once a camera reports in"
        icon={Video}
        title="no cameras registered"
      />
    )
  }

  return (
    <ConsoleBody
      cameras={cameras}
      initialCameraId={initialCameraId}
      initialFilter={initialFilter}
    />
  )
}
