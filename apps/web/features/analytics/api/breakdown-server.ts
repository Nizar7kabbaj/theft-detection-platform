import { type DateRange, endInstant, startInstant } from "@/features/analytics/api/date-range"
import { type StatsBreakdown, statsBreakdownSchema } from "@/features/analytics/schemas/breakdown"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export function breakdownPath(range: DateRange): string {
  const search = new URLSearchParams()
  if (range.start !== null) {
    search.set("start", startInstant(range.start))
  }
  if (range.end !== null) {
    search.set("end", endInstant(range.end))
  }
  const query = search.toString()
  return query === "" ? "/api/v1/stats/breakdown" : `/api/v1/stats/breakdown?${query}`
}

export async function fetchStatsBreakdown(range: DateRange): Promise<StatsBreakdown | null> {
  try {
    return await serverRead(breakdownPath(range), { schema: statsBreakdownSchema })
  } catch {
    return null
  }
}
