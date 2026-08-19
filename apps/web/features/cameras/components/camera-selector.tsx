import type { Route } from "next"
import Link from "next/link"
import { HEALTH_DOT, HEALTH_LABEL } from "@/features/cameras/lib/health"
import { type Camera, cameraHealth } from "@/features/cameras/schemas/camera"

const ROW_CLASS =
  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring aria-[current=page]:bg-accent aria-[current=page]:font-medium"

export function CameraSelector({ cameras, currentId }: { cameras: Camera[]; currentId: string }) {
  return (
    <nav aria-label="cameras" className="flex min-w-0 flex-col gap-1">
      <span className="px-2.5 pb-1 text-muted-foreground text-xs uppercase tracking-wide">
        cameras
      </span>
      {cameras.length === 0 ? (
        <p className="px-2.5 py-2 text-muted-foreground text-sm">no cameras registered</p>
      ) : (
        cameras.map((camera) => {
          const state = cameraHealth(camera).state
          const current = camera.camera_id === currentId
          const href = `/cameras/${encodeURIComponent(camera.camera_id)}` as Route
          return (
            <Link
              key={camera.camera_id}
              href={href}
              aria-current={current ? "page" : undefined}
              className={ROW_CLASS}
            >
              <span
                aria-hidden="true"
                className={`size-2 shrink-0 rounded-full ${HEALTH_DOT[state]} ${
                  state === "online" ? "animate-pulse" : ""
                }`}
              />
              <span className="min-w-0 flex-1 truncate">{camera.name}</span>
              <span className="sr-only">{HEALTH_LABEL[state]}</span>
            </Link>
          )
        })
      )}
    </nav>
  )
}
