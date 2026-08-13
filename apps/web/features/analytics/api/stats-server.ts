import "server-only"
import { type Stats, statsResponseSchema } from "@/features/analytics/schemas/stats"
import { serverRead } from "@/lib/dal/request"

export function fetchStats(): Promise<Stats> {
  return serverRead("/api/v1/stats", { schema: statsResponseSchema })
}
