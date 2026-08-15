import type { Alert } from "@/features/alerts/schemas/alert"

export type AlertSeverity = Alert["severity"]

export const SEVERITY_VALUES = [
  "SEVERITY_UNSPECIFIED",
  "SEVERITY_INFO",
  "SEVERITY_NOTICE",
  "SEVERITY_WARNING",
  "SEVERITY_CRITICAL",
] as const satisfies readonly AlertSeverity[]

type UncoveredSeverity = Exclude<AlertSeverity, (typeof SEVERITY_VALUES)[number]>
type AssertNever<T extends never> = T
export type SeverityDrift = AssertNever<UncoveredSeverity>

export const ALERT_PAGE_SIZE = 50

export type AlertFilters = {
  severity: AlertSeverity | null
  acknowledged: boolean | null
}

export const EMPTY_FILTERS: AlertFilters = { severity: null, acknowledged: null }

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

export function parseAlertFilters(params: RawParams): AlertFilters {
  return {
    severity: toSeverity(single(params.severity)),
    acknowledged: toAcknowledged(single(params.acknowledged)),
  }
}

export function alertFiltersToSearch(filters: AlertFilters): string {
  const search = new URLSearchParams()
  if (filters.severity !== null) {
    search.set("severity", filters.severity)
  }
  if (filters.acknowledged !== null) {
    search.set("acknowledged", String(filters.acknowledged))
  }
  const encoded = search.toString()
  return encoded === "" ? "" : `?${encoded}`
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
  if (cursor !== null) {
    search.set("cursor", cursor)
  }
  return `/api/v1/alerts?${search.toString()}`
}

export const alertKeys = {
  all: ["alerts"] as const,
  list: (filters: AlertFilters) =>
    ["alerts", "list", filters.severity, filters.acknowledged] as const,
}
