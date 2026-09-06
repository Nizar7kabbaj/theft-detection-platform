import {
  type SystemHistory,
  systemHistoryResponseSchema,
} from "@/features/analytics/schemas/system-history"
import { apiRequest } from "@/lib/api/client"
import "client-only"

export const systemHistoryQueryKey = ["stats", "system", "history"] as const

export function fetchSystemHistoryClient(signal?: AbortSignal): Promise<SystemHistory> {
  if (signal === undefined) {
    return apiRequest("/api/v1/stats/system/history", { schema: systemHistoryResponseSchema })
  }
  return apiRequest("/api/v1/stats/system/history", {
    schema: systemHistoryResponseSchema,
    signal,
  })
}
