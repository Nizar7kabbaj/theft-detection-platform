import type { Alert, Decision } from "@/features/alerts/schemas/alert"
import type { components } from "@/types/api"

export type AlertSeverity = Alert["severity"]
export type AlertSort = components["schemas"]["AlertSort"]
export type CameraOption = {
  id: string
  hasEvents: boolean
}

export const SEVERITY_VALUES = [
  "SEVERITY_UNSPECIFIED",
  "SEVERITY_INFO",
  "SEVERITY_NOTICE",
  "SEVERITY_WARNING",
  "SEVERITY_CRITICAL",
] as const satisfies readonly AlertSeverity[]

export const DECISION_VALUES = [
  "DECISION_UNSPECIFIED",
  "DECISION_CONFIRMED",
  "DECISION_DISMISSED",
  "DECISION_UNSURE",
] as const satisfies readonly Decision[]

export const SORT_VALUES = ["created_at", "decided_at"] as const satisfies readonly AlertSort[]

type UncoveredSeverity = Exclude<AlertSeverity, (typeof SEVERITY_VALUES)[number]>
type UncoveredDecision = Exclude<Decision, (typeof DECISION_VALUES)[number]>
type UncoveredSort = Exclude<AlertSort, (typeof SORT_VALUES)[number]>
type AssertNever<T extends never> = T
export type SeverityDrift = AssertNever<UncoveredSeverity>
export type DecisionDrift = AssertNever<UncoveredDecision>
export type SortDrift = AssertNever<UncoveredSort>

export const ALERT_PAGE_SIZE = 50

export type AlertFilters = {
  severity: AlertSeverity | null
  acknowledged: boolean | null
  camera: string | null
  decision: Decision | null
  sort: AlertSort | null
}

export const EMPTY_FILTERS: AlertFilters = {
  severity: null,
  acknowledged: null,
  camera: null,
  decision: null,
  sort: null,
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

function toSeverity(value: string | null): AlertSeverity | null {
  if (value === null) {
    return null
  }
  const match = SEVERITY_VALUES.find((candidate) => candidate === value)
  return match ?? null
}

function toAcknowledged(value: string | null): boolean | null {
  if (value === "true") {
    return true
  }
  if (value === "false") {
    return false
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

function toSort(value: string | null): AlertSort | null {
  if (value === null) {
    return null
  }
  const match = SORT_VALUES.find((candidate) => candidate === value)
  return match ?? null
}

function toCamera(value: string | null): string | null {
  if (value === null || value.length > 128) {
    return null
  }
  return value
}

export function parseAlertFilters(params: RawParams): AlertFilters {
  return {
    severity: toSeverity(single(params.severity)),
    acknowledged: toAcknowledged(single(params.acknowledged)),
    camera: toCamera(single(params.camera)),
    decision: toDecision(single(params.decision)),
    sort: toSort(single(params.sort)),
  }
}

function applyFilters(search: URLSearchParams, filters: AlertFilters): void {
  if (filters.severity !== null) {
    search.set("severity", filters.severity)
  }
  if (filters.acknowledged !== null) {
    search.set("acknowledged", String(filters.acknowledged))
  }
  if (filters.camera !== null) {
    search.set("camera", filters.camera)
  }
  if (filters.decision !== null) {
    search.set("decision", filters.decision)
  }
  if (filters.sort !== null) {
    search.set("sort", filters.sort)
  }
}

export function alertFiltersToSearch(filters: AlertFilters): string {
  const search = new URLSearchParams()
  applyFilters(search, filters)
  const encoded = search.toString()
  return encoded === "" ? "" : `?${encoded}`
}

export function activeFilterCount(filters: AlertFilters): number {
  let count = 0
  if (filters.severity !== null) {
    count += 1
  }
  if (filters.acknowledged !== null) {
    count += 1
  }
  if (filters.camera !== null) {
    count += 1
  }
  if (filters.decision !== null) {
    count += 1
  }
  if (filters.sort !== null) {
    count += 1
  }
  return count
}

export function alertListPath(filters: AlertFilters, cursor: string | null): string {
  const search = new URLSearchParams()
  search.set("limit", String(ALERT_PAGE_SIZE))
  if (filters.severity !== null) {
    search.set("severity", filters.severity)
  }
  if (filters.acknowledged !== null) {
    search.set("acknowledged", String(filters.acknowledged))
  }
  if (filters.camera !== null) {
    search.set("camera_id", filters.camera)
  }
  if (filters.decision !== null) {
    search.set("decision", filters.decision)
  }
  if (filters.sort !== null) {
    search.set("sort", filters.sort)
  }
  if (cursor !== null) {
    search.set("cursor", cursor)
  }
  return `/api/v1/alerts?${search.toString()}`
}

export const alertKeys = {
  all: ["alerts"] as const,
  list: (filters: AlertFilters) =>
    [
      "alerts",
      "list",
      filters.severity,
      filters.acknowledged,
      filters.camera,
      filters.decision,
      filters.sort,
    ] as const,
  detail: (id: string) => ["alerts", "detail", id] as const,
}
