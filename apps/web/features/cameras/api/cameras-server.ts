import { CAMERA_LIST_PATH } from "@/features/cameras/api/camera-keys"
import { type Camera, cameraListSchema } from "@/features/cameras/schemas/camera"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export function fetchCameras(): Promise<Camera[]> {
  return serverRead(CAMERA_LIST_PATH, { schema: cameraListSchema })
}
