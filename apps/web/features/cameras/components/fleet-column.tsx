"use client"

import { useMemo, useState } from "react"
import {
  FLEET_FILTER_COOKIE_MAX_AGE,
  FLEET_FILTER_COOKIE_NAME,
  FLEET_FILTERS,
  type FleetFilter,
} from "@/features/cameras/api/camera-cookie"
import { FleetTile } from "@/features/cameras/components/fleet-tile"
import { type Camera, cameraHealth } from "@/features/cameras/schemas/camera"
import { writeCookie } from "@/lib/cookies/write"

export function FleetColumn({
  cameras,
  selectedId,
  onSelect,
  initialFilter,
}: {
  cameras: Camera[]
  selectedId: string
  onSelect: (cameraId: string) => void
  initialFilter: FleetFilter
}) {
  const [filter, setFilter] = useState<FleetFilter>(initialFilter)
  const [term, setTerm] = useState("")

  const choose = (option: FleetFilter): void => {
    setFilter(option)
    writeCookie(FLEET_FILTER_COOKIE_NAME, option, FLEET_FILTER_COOKIE_MAX_AGE)
  }

  const rows = useMemo(() => {
    const needle = term.trim().toLowerCase()
    return cameras.filter((camera) => {
      if (filter !== "all" && cameraHealth(camera).state !== filter) {
        return false
      }
      if (needle === "") {
        return true
      }
      return (
        camera.name.toLowerCase().includes(needle) ||
        camera.camera_id.toLowerCase().includes(needle) ||
        camera.location.toLowerCase().includes(needle)
      )
    })
  }, [cameras, filter, term])

  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <input
        aria-label="find camera or zone"
        className="h-8 w-full min-w-0 rounded-sm border border-border bg-background px-2.5 text-xs outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
        onChange={(event) => setTerm(event.target.value)}
        placeholder="find camera or zone"
        type="search"
        value={term}
      />
      <div className="flex flex-wrap gap-1">
        {FLEET_FILTERS.map((option) => (
          <button
            aria-pressed={filter === option}
            className={`rounded-sm px-2 py-1 font-mono text-[10px] uppercase outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring ${
              filter === option
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
            key={option}
            onClick={() => choose(option)}
            type="button"
          >
            {option}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <p className="rounded-lg border border-border border-dashed px-3 py-6 text-center font-mono text-[10px] text-muted-foreground uppercase">
          no camera matches
        </p>
      ) : (
        rows.map((camera) => (
          <FleetTile
            camera={camera}
            key={camera._id}
            onSelect={onSelect}
            selected={camera.camera_id === selectedId}
          />
        ))
      )}
    </div>
  )
}
