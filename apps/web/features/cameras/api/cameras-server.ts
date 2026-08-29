import { cache } from "react"
import { CAMERA_LIST_PATH } from "@/features/cameras/api/camera-keys"
import { type Camera, cameraListSchema, cameraSchema } from "@/features/cameras/schemas/camera"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export const fetchCameras = cache(function fetchCameras(): Promise<Camera[]> {
  return serverRead(CAMERA_LIST_PATH, { schema: cameraListSchema })
})
export const fetchCamera = cache(function fetchCamera(cameraId: string): Promise<Camera> {
  return serverRead(`${CAMERA_LIST_PATH}/${encodeURIComponent(cameraId)}`, {
    schema: cameraSchema,
  })
})
