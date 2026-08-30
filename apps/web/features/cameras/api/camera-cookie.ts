export const CAMERA_COOKIE_NAME = "selected_camera"
export const CAMERA_COOKIE_MAX_AGE = 60 * 60 * 24 * 30

export function parseCameraId(value: string | undefined | null): string | null {
  if (value === undefined || value === null) {
    return null
  }
  const trimmed = value.trim()
  if (trimmed === "" || trimmed.length > 128) {
    return null
  }
  return trimmed
}

export const FLEET_FILTER_COOKIE_NAME = "fleet_filter"
export const FLEET_FILTER_COOKIE_MAX_AGE = 60 * 60 * 24 * 30

export const FLEET_FILTERS = ["all", "online", "degraded", "offline"] as const
export type FleetFilter = (typeof FLEET_FILTERS)[number]

export function parseFleetFilter(value: string | undefined | null): FleetFilter {
  const match = FLEET_FILTERS.find((candidate) => candidate === value)
  return match ?? "all"
}
