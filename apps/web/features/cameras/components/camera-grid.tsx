"use client"
import { Video } from "lucide-react"
import { EmptyState } from "@/components/ui/empty-state"
import { CameraTile } from "@/features/cameras/components/camera-tile"
import { useCameraGrid } from "@/features/cameras/hooks/use-camera-grid"

const SKELETON_KEYS = ["a", "b", "c"] as const

export function CameraGrid() {
  const { cameras, isPending, isError } = useCameraGrid()

  if (isError) {
    return (
      <EmptyState
        icon={Video}
        title="cameras unavailable"
        description="the camera list could not be loaded. check the connection and retry."
      />
    )
  }

  if (isPending) {
    return (
      <div aria-busy="true" className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
        {SKELETON_KEYS.map((placeholder) => (
          <div
            className="h-32 animate-pulse rounded-xl bg-muted/40 ring-1 ring-foreground/10"
            key={placeholder}
          />
        ))}
      </div>
    )
  }

  if (cameras.length === 0) {
    return (
      <EmptyState
        icon={Video}
        title="no cameras registered"
        description="capture sources appear here once a camera reports in"
      />
    )
  }

  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
      {cameras.map((camera) => (
        <CameraTile camera={camera} key={camera._id} />
      ))}
    </div>
  )
}
