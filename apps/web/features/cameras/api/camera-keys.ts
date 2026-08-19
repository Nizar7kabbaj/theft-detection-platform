export const CAMERA_LIST_PATH = "/api/v1/cameras"

export const cameraKeys = {
  all: ["cameras"] as const,
  list: () => ["cameras", "list"] as const,
}
