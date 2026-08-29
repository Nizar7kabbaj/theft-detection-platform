import { type AlertSeverity, SEVERITY_VALUES } from "@/features/alerts/api/alert-keys"
import type { Decision } from "@/features/alerts/schemas/alert"
import type { components } from "@/types/api"

export type AlertSort = components["schemas"]["AlertSort"]

export const DECISION_VALUES = [
  "DECISION_UNSPECIFIED",
  "DECISION_CONFIRMED",
  "DECISION_DISMISSED",
  "DECISION_UNSURE",
] as const satisfies readonly Decision[]

export const SORT_VALUES = ["decided_at", "created_at"] as const satisfies readonly AlertSort[]

type UncoveredDecision = Exclude<Decision, (typeof DECISION_VALUES)[number]>
type UncoveredSort = Exclude<AlertSort, (typeof SORT_VALUES)[number]>
type AssertNever<T extends never> = T
export type DecisionDrift = AssertNever<UncoveredDecision>
export type SortDrift = AssertNever<UncoveredSort>

export const RANGE_VALUES = ["today", "7d", "30d"] as const
export type HistoryRange = (typeof RANGE_VALUES)[number]
export const DEFAULT_RANGE: HistoryRange = "30d"

export const HISTORY_PAGE_SIZE = 25
export const DEFAULT_SORT: AlertSort = "created_at"

const CAMERA_ID_MAX_LENGTH = 64
const DAY_MS = 86_400_000
const RANGE_DAYS: Record<HistoryRange, number> = { today: 0, "7d": 7, "30d": 30 }

export type HistoryFilters = {
  range: HistoryRange
  decision: Decision | null
  severity: AlertSeverity | null
  camera: string | null
  sort: AlertSort
}

export const DEFAULT_FILTERS: HistoryFilters = {
  range: DEFAULT_RANGE,
  decision: null,
  severity: null,
  camera: null,
  sort: DEFAULT_SORT,
}

export type RangeBounds = { start: string; end: string }

export function rangeBounds(range: HistoryRange, now: Date): RangeBounds {
  const end = now
  if (range === "today") {
    const start = new Date(
      Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0, 0),
    )
    return { start: start.toISOString(), end: end.toISOString() }
  }
  const start = new Date(end.getTime() - RANGE_DAYS[range] * DAY_MS)
  return { start: start.toISOString(), end: end.toISOString() }
}

export function bucketUnit(range: HistoryRange): "hour" | "day" {
  return range === "today" ? "hour" : "day"
}

type RawParams = Record<string, string | string[] | undefined>

function single(value: string | string[] | undefined): string | null {
  if (typeof value === "string") {
    return value === "" ? null : value
  }
  if (Array.isArray(value)) {
    const first = value[0]
    return first === undefined || first === "" ? null : first
  }
  return null
}

function toRange(value: string | null): HistoryRange {
  if (value === null) {
    return DEFAULT_RANGE
  }
  const match = RANGE_VALUES.find((candidate) => candidate === value)
  return match ?? DEFAULT_RANGE
}

function toDecision(value: string | null): Decision | null {
  if (value === null) {
    return null
  }
  const match = DECISION_VALUES.find((candidate) => candidate === value)
  return match ?? null
}

function toSeverity(value: string | null): AlertSeverity | null {
  if (value === null) {
    return null
  }
  const match = SEVERITY_VALUES.find((candidate) => candidate === value)
  return match ?? null
}

function toCamera(value: string | null): string | null {
  if (value === null) {
    return null
  }
  const trimmed = value.trim()
  if (trimmed === "" || trimmed.length > CAMERA_ID_MAX_LENGTH) {
    return null
  }
  return trimmed
}

function toSort(value: string | null): AlertSort {
  if (value === null) {
    return DEFAULT_SORT
  }
  const match = SORT_VALUES.find((candidate) => candidate === value)
  return match ?? DEFAULT_SORT
}

export function parseHistoryFilters(params: RawParams): HistoryFilters {
  return {
    range: toRange(single(params.range)),
    decision: toDecision(single(params.decision)),
    severity: toSeverity(single(params.severity)),
    camera: toCamera(single(params.camera_id)),
    sort: toSort(single(params.sort)),
  }
}

export function parseHistoryCursor(params: RawParams): string | null {
  return single(params.cursor)
}

function searchFor(filters: HistoryFilters, cursor: string | null): URLSearchParams {
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
  if (cursor !== null) {
    search.set("cursor", cursor)
  }
  return search
}

export function historyListPath(
  filters: HistoryFilters,
  cursor: string | null,
  bounds: RangeBounds,
): string {
  const search = searchFor(filters, cursor)
  search.delete("range")
  search.set("start", bounds.start)
  search.set("end", bounds.end)
  search.set("limit", String(HISTORY_PAGE_SIZE))
  return `/api/v1/alerts?${search.toString()}`
}

export function historyHref(filters: HistoryFilters, cursor: string | null): string {
  return `/history?${searchFor(filters, cursor).toString()}`
}
