import { type AlertFilters, parseAlertFilters } from "@/features/alerts/api/alert-keys"

export const ALERT_FILTERS_COOKIE_NAME = "alert_filters"
export const ALERT_FILTERS_COOKIE_MAX_AGE = 60 * 60 * 24 * 30

const MAX_COOKIE_LENGTH = 512
const FILTER_KEYS = ["severity", "acknowledged", "camera", "decision", "sort"] as const

export function hasFilterParams(params: Record<string, string | string[] | undefined>): boolean {
  return FILTER_KEYS.some((key) => params[key] !== undefined)
}

export function parseStoredFilters(value: string | undefined | null): AlertFilters | null {
  if (value === undefined || value === null || value === "" || value.length > MAX_COOKIE_LENGTH) {
    return null
  }
  let decoded: string
  try {
    decoded = decodeURIComponent(value)
  } catch {
    return null
  }
  const search = new URLSearchParams(decoded)
  const raw: Record<string, string> = {}
  for (const key of FILTER_KEYS) {
    const found = search.get(key)
    if (found !== null) {
      raw[key] = found
    }
  }
  if (Object.keys(raw).length === 0) {
    return null
  }
  return parseAlertFilters(raw)
}
