import "server-only"
import { cache } from "react"
import { type Stats, statsResponseSchema } from "@/features/analytics/schemas/stats"
import { serverRead } from "@/lib/dal/request"

export const fetchStats = cache(function fetchStats(): Promise<Stats> {
  return serverRead("/api/v1/stats", { schema: statsResponseSchema })
})
