import {
  type SystemStats,
  systemStatsResponseSchema,
} from "@/features/analytics/schemas/system-stats"
import { apiRequest } from "@/lib/api/client"
import "client-only"

export const systemStatsQueryKey = ["stats", "system"] as const

export function fetchSystemStatsClient(signal?: AbortSignal): Promise<SystemStats> {
  if (signal === undefined) {
    return apiRequest("/api/v1/stats/system", { schema: systemStatsResponseSchema })
  }
  return apiRequest("/api/v1/stats/system", { schema: systemStatsResponseSchema, signal })
}
