import type { CameraOption } from "@/features/alerts/api/alert-keys"
import { fetchCameras } from "@/features/cameras/api/cameras-server"
import { fetchAlertCameras } from "@/features/history/api/camera-facet"
import "server-only"

export async function fetchCameraOptions(): Promise<CameraOption[]> {
  const [withEvents, fleet] = await Promise.all([
    fetchAlertCameras(),
    fetchCameras().catch(() => []),
  ])

  const eventIds = new Set(withEvents)
  const seen = new Set<string>()
  const options: CameraOption[] = []

  for (const id of withEvents) {
    if (seen.has(id)) {
      continue
    }
    seen.add(id)
    options.push({ id, hasEvents: true })
  }

  for (const camera of fleet) {
    if (seen.has(camera.camera_id) || eventIds.has(camera.camera_id)) {
      continue
    }
    seen.add(camera.camera_id)
    options.push({ id: camera.camera_id, hasEvents: false })
  }

  return options
}
