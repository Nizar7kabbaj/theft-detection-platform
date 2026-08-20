import type { BucketUnit } from "@/features/analytics/schemas/timeseries"

export type DateRange = {
  start: string | null
  end: string | null
}

export const EMPTY_RANGE: DateRange = { start: null, end: null }

export const PRESET_DAYS = [7, 30, 90] as const
export type PresetDays = (typeof PRESET_DAYS)[number]

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

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
  return `${day}T00:00:00Z`
}

export function endInstant(day: string): string {
  return `${day}T23:59:59Z`
}

export function todayUtc(): string {
  return new Date().toISOString().slice(0, 10)
}

export function shiftDays(day: string, days: number): string {
  const at = new Date(`${day}T00:00:00Z`)
  at.setUTCDate(at.getUTCDate() + days)
  return at.toISOString().slice(0, 10)
}

export function presetRange(days: PresetDays): DateRange {
  const end = todayUtc()
  return { start: shiftDays(end, -(days - 1)), end }
}

export function bucketCount(range: DateRange, unit: BucketUnit): number | null {
  if (range.start === null || range.end === null) {
    return null
  }
  const spanDays =
    (Date.parse(`${range.end}T00:00:00Z`) - Date.parse(`${range.start}T00:00:00Z`)) / 86400000 + 1
  return unit === "day" ? spanDays : spanDays * 24
}
