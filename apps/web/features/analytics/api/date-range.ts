import type { BucketUnit } from "@/features/analytics/schemas/timeseries"
import { STORE_TIME_ZONE } from "@/lib/time/zone"

export type DateRange = {
  start: string | null
  end: string | null
}

export const EMPTY_RANGE: DateRange = { start: null, end: null }
export const PRESET_DAYS = [7, 30, 90] as const
export type PresetDays = (typeof PRESET_DAYS)[number]

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const OFFSET_PATTERN = /GMT([+-]\d{2}:\d{2})/
const DAY_MS = 86400000

const OFFSET_FORMAT = new Intl.DateTimeFormat("en-US", {
  timeZone: STORE_TIME_ZONE,
  timeZoneName: "longOffset",
})

const DAY_FORMAT = new Intl.DateTimeFormat("en-CA", {
  timeZone: STORE_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
})

function storeOffset(at: Date): string {
  const part = OFFSET_FORMAT.formatToParts(at).find((entry) => entry.type === "timeZoneName")
  const matched = part === undefined ? null : OFFSET_PATTERN.exec(part.value)
  return matched?.[1] ?? "+00:00"
}

function toDate(value: string | string[] | undefined): string | null {
  const raw = typeof value === "string" ? value : Array.isArray(value) ? value[0] : undefined
  if (raw === undefined || !DATE_PATTERN.test(raw)) {
    return null
  }
  return Number.isNaN(Date.parse(`${raw}T00:00:00Z`)) ? null : raw
}

export function parseDateRange(params: Record<string, string | string[] | undefined>): DateRange {
  const start = toDate(params.start)
  const end = toDate(params.end)
  if (start !== null && end !== null && start > end) {
    return EMPTY_RANGE
  }
  return { start, end }
}

export function startInstant(day: string): string {
  return `${day}T00:00:00${storeOffset(new Date(`${day}T12:00:00Z`))}`
}

export function endInstant(day: string): string {
  return `${day}T23:59:59${storeOffset(new Date(`${day}T12:00:00Z`))}`
}

export function today(): string {
  return DAY_FORMAT.format(new Date())
}

export function shiftDays(day: string, days: number): string {
  const at = new Date(Date.parse(`${day}T12:00:00Z`) + days * DAY_MS)
  return at.toISOString().slice(0, 10)
}

export function presetRange(days: PresetDays): DateRange {
  const end = today()
  return { start: shiftDays(end, -(days - 1)), end }
}

export function bucketCount(range: DateRange, unit: BucketUnit): number | null {
  if (range.start === null || range.end === null) {
    return null
  }
  const spanDays =
    (Date.parse(`${range.end}T12:00:00Z`) - Date.parse(`${range.start}T12:00:00Z`)) / DAY_MS + 1
  return unit === "day" ? spanDays : spanDays * 24
}
