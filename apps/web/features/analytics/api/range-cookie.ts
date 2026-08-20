import { DEFAULT_UNIT, parseBucketUnit } from "@/features/analytics/api/bucket-unit"
import { type DateRange, EMPTY_RANGE, parseDateRange } from "@/features/analytics/api/date-range"
import type { BucketUnit } from "@/features/analytics/schemas/timeseries"

export const RANGE_COOKIE_NAME = "analytics_range"
export const RANGE_COOKIE_MAX_AGE = 60 * 60 * 24 * 30

export type RangeSelection = {
  range: DateRange
  unit: BucketUnit
}

export const DEFAULT_SELECTION: RangeSelection = { range: EMPTY_RANGE, unit: DEFAULT_UNIT }

export function encodeSelection(selection: RangeSelection): string {
  return [selection.range.start ?? "", selection.range.end ?? "", selection.unit].join("|")
}

export function decodeSelection(value: string | undefined): RangeSelection {
  if (value === undefined || value === "") {
    return DEFAULT_SELECTION
  }
  const parts = value.split("|")
  if (parts.length !== 3) {
    return DEFAULT_SELECTION
  }
  const [start, end, unit] = parts
  return {
    range: parseDateRange({ start, end }),
    unit: parseBucketUnit({ unit }),
  }
}

export function selectionSearch(selection: RangeSelection): string {
  const search = new URLSearchParams()
  if (selection.range.start !== null) {
    search.set("start", selection.range.start)
  }
  if (selection.range.end !== null) {
    search.set("end", selection.range.end)
  }
  search.set("unit", selection.unit)
  return search.toString()
}
