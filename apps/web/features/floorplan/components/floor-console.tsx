"use client"
import { useCallback, useMemo, useState } from "react"
import { LiveView } from "@/features/cameras/components/live-view"
import { useCameraGrid } from "@/features/cameras/hooks/use-camera-grid"
import { HEALTH_DETAIL, HEALTH_DOT, HEALTH_TEXT } from "@/features/cameras/lib/health"
import { type Camera, cameraHealth, type HealthState } from "@/features/cameras/schemas/camera"
import { StoreScene } from "@/features/floorplan/components/store-scene"
import { PLACEMENTS, uncoveredZones } from "@/features/floorplan/lib/coverage"
import { usePlanPalette } from "@/features/floorplan/lib/palette"
import { ZONE_LABEL } from "@/features/floorplan/lib/zones"

const SURFACE_CLASS = "aspect-[16/10] w-full animate-pulse rounded-lg bg-muted"

function stateOf(camera: Camera | undefined): HealthState {
  return camera === undefined ? "unknown" : cameraHealth(camera).state
}

export function FloorConsole() {
  const { cameras, isPending, isError } = useCameraGrid()
  const palette = usePlanPalette()
  const [selected, setSelected] = useState<string | null>(null)

  const byId = useMemo(() => {
    const map = new Map<string, Camera>()
    for (const camera of cameras) {
      map.set(camera.camera_id, camera)
    }
    return map
  }, [cameras])

  const health = useMemo(() => {
    const record: Record<string, HealthState> = {}
    for (const placement of PLACEMENTS) {
      record[placement.cameraId] = stateOf(byId.get(placement.cameraId))
    }
    return record
  }, [byId])

  const select = useCallback((cameraId: string) => {
    setSelected((current) => (current === cameraId ? null : cameraId))
  }, [])

  const blind = useMemo(() => uncoveredZones(), [])
  const active = selected === null ? undefined : byId.get(selected)

  return (
    <div className="grid min-w-0 gap-5 2xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="flex min-w-0 flex-col gap-4">
        {palette === null ? (
          <div className={SURFACE_CLASS} />
        ) : (
          <StoreScene palette={palette} health={health} selected={selected} onSelect={select} />
        )}
        <div className="flex flex-wrap items-center gap-2">
          {PLACEMENTS.map((placement) => {
            const camera = byId.get(placement.cameraId)
            const state = health[placement.cameraId] ?? "unknown"
            const isActive = placement.cameraId === selected
            return (
              <button
                key={placement.cameraId}
                type="button"
                aria-pressed={isActive}
                onClick={() => {
                  select(placement.cameraId)
                }}
                className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors ${
                  isActive ? "border-foreground/40 bg-accent" : "border-border hover:bg-accent/50"
                }`}
              >
                <span aria-hidden="true" className={`size-2 rounded-full ${HEALTH_DOT[state]}`} />
                <span>{camera === undefined ? placement.cameraId : camera.name}</span>
                <span className={`text-xs ${HEALTH_TEXT[state]}`}>{HEALTH_DETAIL[state]}</span>
              </button>
            )
          })}
        </div>
        {blind.length === 0 ? null : (
          <p className="text-muted-foreground text-sm">
            no camera covers {blind.map((zone) => ZONE_LABEL[zone]).join(", ")}
          </p>
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-3">
        {isError ? (
          <p className="text-muted-foreground text-sm">camera list is unavailable</p>
        ) : isPending ? (
          <div className="aspect-video w-full animate-pulse rounded-xl bg-muted" />
        ) : active === undefined ? (
          <div className="flex aspect-video w-full items-center justify-center rounded-xl border border-border border-dashed px-6 text-center text-muted-foreground text-sm">
            pick a camera on the floor to open its stream
          </div>
        ) : (
          <LiveView
            cameraId={active.camera_id}
            cameraName={active.name}
            lastFrameAt={cameraHealth(active).last_frame_at ?? null}
          />
        )}
      </div>
    </div>
  )
}
