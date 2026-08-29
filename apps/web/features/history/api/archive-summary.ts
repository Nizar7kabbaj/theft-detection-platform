import type { Decision } from "@/features/alerts/schemas/alert"
import { statsTimeseriesSchema } from "@/features/analytics/schemas/timeseries"
import {
  bucketUnit,
  type HistoryFilters,
  type RangeBounds,
} from "@/features/history/api/history-keys"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export type SeverityTally = {
  critical: number
  warning: number
  notice: number
  info: number
}

export type ArchiveSummary = {
  total: number
  decided: number
  undecided: number
  decisions: Record<Exclude<Decision, "DECISION_UNSPECIFIED">, number>
  severity: SeverityTally
  volume: readonly number[]
  first: string | null
  last: string | null
}

const EMPTY: ArchiveSummary = {
  total: 0,
  decided: 0,
  undecided: 0,
  decisions: { DECISION_CONFIRMED: 0, DECISION_DISMISSED: 0, DECISION_UNSURE: 0 },
  severity: { critical: 0, warning: 0, notice: 0, info: 0 },
  volume: [],
  first: null,
  last: null,
}

export async function fetchArchiveSummary(
  filters: HistoryFilters,
  bounds: RangeBounds,
): Promise<ArchiveSummary> {
  const search = new URLSearchParams({
    start: bounds.start,
    end: bounds.end,
    unit: bucketUnit(filters.range),
  })
  try {
    const data = await serverRead(`/api/v1/stats/timeseries?${search.toString()}`, {
      schema: statsTimeseriesSchema,
    })
    let total = 0
    let decided = 0
    const severity: SeverityTally = { critical: 0, warning: 0, notice: 0, info: 0 }
    const volume: number[] = []
    for (const bucket of data.alerts) {
      total += bucket.total
      severity.critical += bucket.critical
      severity.warning += bucket.warning
      severity.notice += bucket.notice
      severity.info += bucket.info
      volume.push(bucket.total)
    }
    const decisions = { DECISION_CONFIRMED: 0, DECISION_DISMISSED: 0, DECISION_UNSURE: 0 }
    for (const bucket of data.decisions) {
      decided += bucket.total
      decisions.DECISION_CONFIRMED += bucket.confirmed
      decisions.DECISION_DISMISSED += bucket.dismissed
      decisions.DECISION_UNSURE += bucket.unsure
    }
    return {
      total,
      decided,
      undecided: Math.max(total - decided, 0),
      decisions,
      severity,
      volume,
      first: data.start,
      last: data.end,
    }
  } catch {
    return EMPTY
  }
}
