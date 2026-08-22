"use client"
import { useSearchParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useState } from "react"
import { LiveView } from "@/features/cameras/components/live-view"
import { useCameraGrid } from "@/features/cameras/hooks/use-camera-grid"
import { HEALTH_DETAIL, HEALTH_DOT, HEALTH_TEXT } from "@/features/cameras/lib/health"
import { type Camera, cameraHealth, type HealthState } from "@/features/cameras/schemas/camera"
import { StoreScene } from "@/features/floorplan/components/store-scene"
import { PLACEMENTS, uncoveredZones } from "@/features/floorplan/lib/coverage"
import { usePlanPalette } from "@/features/floorplan/lib/palette"
import { ZONE_LABEL } from "@/features/floorplan/lib/zones"

const SURFACE_CLASS = "aspect-[16/10] w-full animate-pulse rounded-lg bg-muted"
const CAMERA_PARAM = "camera"
const CAMERA_STORAGE_KEY = "floorplan.camera"
const PLACED_IDS: ReadonlySet<string> = new Set(PLACEMENTS.map((placement) => placement.cameraId))

function placed(cameraId: string | null): string | null {
  return cameraId !== null && PLACED_IDS.has(cameraId) ? cameraId : null
}

function readStored(): string | null {
  try {
    return window.sessionStorage.getItem(CAMERA_STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStored(cameraId: string | null): void {
  try {
    if (cameraId === null) {
      window.sessionStorage.removeItem(CAMERA_STORAGE_KEY)
      return
    }
    window.sessionStorage.setItem(CAMERA_STORAGE_KEY, cameraId)
  } catch {
    return
  }
}

function stateOf(camera: Camera | undefined): HealthState {
  return camera === undefined ? "unknown" : cameraHealth(camera).state
}

export function FloorConsole() {
  const { cameras, isPending, isError } = useCameraGrid()
  const palette = usePlanPalette()
  const params = useSearchParams()
  const fromUrl = params.get(CAMERA_PARAM)

  const [selected, setSelected] = useState<string | null>(
    () => placed(fromUrl) ?? placed(readStored()),
  )

  useEffect(() => {
    writeStored(selected)
    const search = new URLSearchParams(window.location.search)
    if (selected === null) {
      search.delete(CAMERA_PARAM)
    } else {
      search.set(CAMERA_PARAM, selected)
    }
    const query = search.toString()
    const target = query === "" ? window.location.pathname : `${window.location.pathname}?${query}`
    if (target !== `${window.location.pathname}${window.location.search}`) {
      window.history.replaceState(null, "", target)
    }
  }, [selected])

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
