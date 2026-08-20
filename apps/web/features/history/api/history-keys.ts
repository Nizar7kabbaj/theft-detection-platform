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

export const HISTORY_PAGE_SIZE = 25
export const DEFAULT_SORT: AlertSort = "decided_at"
const CAMERA_ID_MAX_LENGTH = 128

export type HistoryFilters = {
  decision: Decision | null
  severity: AlertSeverity | null
  camera: string | null
  sort: AlertSort
}

export const DEFAULT_FILTERS: HistoryFilters = {
  decision: null,
  severity: null,
  camera: null,
  sort: DEFAULT_SORT,
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

export function historyListPath(filters: HistoryFilters, cursor: string | null): string {
  const search = searchFor(filters, cursor)
  search.set("limit", String(HISTORY_PAGE_SIZE))
  return `/api/v1/alerts?${search.toString()}`
}

export function historyHref(filters: HistoryFilters, cursor: string | null): string {
  const encoded = searchFor(filters, cursor).toString()
  return encoded === "" ? "/history" : `/history?${encoded}`
}
