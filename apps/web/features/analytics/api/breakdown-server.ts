import { type DateRange, endInstant, startInstant } from "@/features/analytics/api/date-range"
import { type StatsBreakdown, statsBreakdownSchema } from "@/features/analytics/schemas/breakdown"
import type { BucketUnit } from "@/features/analytics/schemas/timeseries"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export function breakdownPath(range: DateRange, unit: BucketUnit): string {
  const search = new URLSearchParams({ unit })
  if (range.start !== null) {
    search.set("start", startInstant(range.start))
  }
  if (range.end !== null) {
    search.set("end", endInstant(range.end))
  }
  return `/api/v1/stats/breakdown?${search.toString()}`
}

export async function fetchStatsBreakdown(
  range: DateRange,
  unit: BucketUnit,
): Promise<StatsBreakdown | null> {
  try {
    return await serverRead(breakdownPath(range, unit), { schema: statsBreakdownSchema })
  } catch {
    return null
  }
}
