import { type DateRange, endInstant, startInstant } from "@/features/analytics/api/date-range"
import {
  type BucketUnit,
  type StatsTimeseries,
  statsTimeseriesSchema,
} from "@/features/analytics/schemas/timeseries"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export function timeseriesPath(unit: BucketUnit, range: DateRange): string {
  const search = new URLSearchParams()
  search.set("unit", unit)
  if (range.start !== null) {
    search.set("start", startInstant(range.start))
  }
  if (range.end !== null) {
    search.set("end", endInstant(range.end))
  }
  return `/api/v1/stats/timeseries?${search.toString()}`
}

export function fetchStatsTimeseries(unit: BucketUnit, range: DateRange): Promise<StatsTimeseries> {
  return serverRead(timeseriesPath(unit, range), { schema: statsTimeseriesSchema })
}
