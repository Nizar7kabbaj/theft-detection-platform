import { type Stats, statsResponseSchema } from "@/features/analytics/schemas/stats"
import { apiRequest } from "@/lib/api/client"
import "client-only"

export function fetchStatsClient(signal?: AbortSignal): Promise<Stats> {
  if (signal === undefined) {
    return apiRequest("/api/v1/stats", { schema: statsResponseSchema })
  }
  return apiRequest("/api/v1/stats", { schema: statsResponseSchema, signal })
}
