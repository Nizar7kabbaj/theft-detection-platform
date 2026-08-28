import type { Route } from "next"
import Link from "next/link"
import { fetchCameras } from "@/features/cameras/api/cameras-server"
import type { HealthState } from "@/features/cameras/schemas/camera"
import { type Camera, cameraHealth } from "@/features/cameras/schemas/camera"
import { cn } from "@/lib/utils"

const DOT: Record<HealthState, string> = {
  online: "bg-success",
  degraded: "bg-warning",
  offline: "bg-destructive",
  unknown: "bg-muted-foreground/50",
}

const DETAIL: Record<HealthState, string> = {
  online: "frames arriving",
  degraded: "frames delayed",
  offline: "no recent frames",
  unknown: "state unknown",
}

const ORDER: Record<HealthState, number> = {
  online: 0,
  degraded: 1,
  unknown: 2,
  offline: 3,
}

function byWorst(left: Camera, right: Camera): number {
  return ORDER[cameraHealth(left).state] - ORDER[cameraHealth(right).state]
}

export async function CameraStatusList() {
  let cameras: Camera[]
  try {
    cameras = await fetchCameras()
  } catch {
    return <p className="font-mono text-[11px] text-muted-foreground">fleet is unavailable</p>
  }

  if (cameras.length === 0) {
    return <p className="font-mono text-[11px] text-muted-foreground">no cameras registered</p>
  }

  return (
    <ul className="flex flex-col">
      {[...cameras].sort(byWorst).map((camera) => {
        const state = cameraHealth(camera).state
        return (
          <li key={camera.camera_id}>
            <Link
              href={`/cameras?id=${encodeURIComponent(camera.camera_id)}` as Route}
              className="flex min-w-0 items-center gap-3 border-border border-b px-1 py-2.5 outline-none transition-colors last:border-b-0 hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="flex min-w-0 flex-col gap-1">
                <span className="truncate text-[12px] leading-none">{camera.name}</span>
                <span className="truncate font-mono text-[10px] text-muted-foreground leading-none">
                  {DETAIL[state]}
                </span>
              </span>
              <span
                aria-hidden="true"
                className={cn("ml-auto size-1.5 shrink-0 rounded-full", DOT[state])}
              />
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
