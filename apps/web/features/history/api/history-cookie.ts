import { type HistoryFilters, parseHistoryFilters } from "@/features/history/api/history-keys"

export const HISTORY_FILTERS_COOKIE_NAME = "history_filters"
export const HISTORY_FILTERS_COOKIE_MAX_AGE = 60 * 60 * 24 * 30

const MAX_COOKIE_LENGTH = 512
const FILTER_KEYS = ["range", "decision", "severity", "camera_id", "sort"] as const

export function hasFilterParams(params: Record<string, string | string[] | undefined>): boolean {
  return FILTER_KEYS.some((key) => params[key] !== undefined)
}

export function parseStoredFilters(value: string | undefined | null): HistoryFilters | null {
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
  return parseHistoryFilters(raw)
}

export function serializeFilters(filters: HistoryFilters): string {
  const search = new URLSearchParams()
  search.set("range", filters.range)
  if (filters.decision !== null) {
    search.set("decision", filters.decision)
  }
  if (filters.severity !== null) {
    search.set("severity", filters.severity)
  }
  if (filters.camera !== null) {
    search.set("camera_id", filters.camera)
  }
  search.set("sort", filters.sort)
  return encodeURIComponent(search.toString())
}
