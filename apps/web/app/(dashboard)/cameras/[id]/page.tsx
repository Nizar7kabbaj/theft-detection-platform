import type { Metadata } from "next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { AbsentPanel } from "@/features/alerts/components/absent-panel"
import { fetchCamera, fetchCameras } from "@/features/cameras/api/cameras-server"
import { CameraSelector } from "@/features/cameras/components/camera-selector"
import { LiveView } from "@/features/cameras/components/live-view"
import { type Camera, cameraHealth } from "@/features/cameras/schemas/camera"

export const metadata: Metadata = { title: "camera" }
export const dynamic = "force-dynamic"

async function safeCameraList(): Promise<Camera[]> {
  try {
    return await fetchCameras()
  } catch {
    return []
  }
}

export default async function CameraDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const [camera, cameras] = await Promise.all([fetchCamera(id), safeCameraList()])
  const health = cameraHealth(camera)

  return (
    <section className="flex flex-1 flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="font-semibold text-2xl">{camera.name}</h1>
        <p className="text-muted-foreground text-sm">
          {camera.location === "" ? "no location recorded" : camera.location}
        </p>
      </header>
      <div className="grid min-w-0 gap-5 lg:grid-cols-[13rem_minmax(0,1fr)_18rem]">
        <aside className="min-w-0 lg:sticky lg:top-5 lg:self-start">
          <CameraSelector cameras={cameras} currentId={camera.camera_id} />
        </aside>
        <div className="flex min-w-0 flex-col gap-5">
          <LiveView
            cameraId={camera.camera_id}
            cameraName={camera.name}
            lastFrameAt={health.last_frame_at ?? null}
          />
          <AbsentPanel
            title="recordings"
            reason="no recording store is wired to this camera, so there is nothing to list"
          />
        </div>
        <div className="flex min-w-0 flex-col gap-5">
          <Card size="sm">
            <CardHeader>
              <CardTitle>camera</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-muted-foreground text-xs">identifier</span>
                <span className="min-w-0 truncate font-mono text-xs">{camera.camera_id}</span>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-muted-foreground text-xs">status</span>
                <span>{camera.status}</span>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-muted-foreground text-xs">source</span>
                <span className="min-w-0 truncate">
                  {camera.stream_url === null || camera.stream_url === undefined
                    ? "no stream url"
                    : camera.stream_url}
                </span>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-muted-foreground text-xs">registered</span>
                <span className="tabular-nums">{camera.created_at.slice(0, 10)}</span>
              </div>
            </CardContent>
          </Card>
          <AbsentPanel
            title="tracking map"
            reason="track history is not stored, so there is nothing to draw on the plan"
          />
          <AbsentPanel
            title="detections"
            reason="detection counts are not aggregated per camera yet"
          />
        </div>
      </div>
    </section>
  )
}
