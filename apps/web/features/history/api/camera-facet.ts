import { serverRead } from "@/lib/dal/request"
import "server-only"
import * as z from "zod/mini"

const ALERT_CAMERAS_PATH = "/api/v1/alerts/cameras"
const CAMERA_ID_MAX_LENGTH = 128

const alertCamerasSchema = z.array(
  z.string().check(z.minLength(1), z.maxLength(CAMERA_ID_MAX_LENGTH)),
)

export async function fetchAlertCameras(): Promise<string[]> {
  try {
    return await serverRead(ALERT_CAMERAS_PATH, { schema: alertCamerasSchema })
  } catch {
    return []
  }
}
