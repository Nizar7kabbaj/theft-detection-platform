import { CAMERA_LIST_PATH } from "@/features/cameras/api/camera-keys"
import { type Camera, cameraListSchema } from "@/features/cameras/schemas/camera"
import { apiRequest } from "@/lib/api/client"
import "client-only"

export function fetchCamerasClient(signal?: AbortSignal): Promise<Camera[]> {
  if (signal === undefined) {
    return apiRequest(CAMERA_LIST_PATH, { schema: cameraListSchema })
  }
  return apiRequest(CAMERA_LIST_PATH, { schema: cameraListSchema, signal })
}
