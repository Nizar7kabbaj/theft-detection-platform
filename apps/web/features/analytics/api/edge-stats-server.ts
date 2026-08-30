import { cache } from "react"
import { type EdgeStats, edgeStatsResponseSchema } from "@/features/analytics/schemas/edge-stats"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export const fetchEdgeStats = cache(function fetchEdgeStats(): Promise<EdgeStats> {
  return serverRead("/api/v1/stats/edge", { schema: edgeStatsResponseSchema })
})
