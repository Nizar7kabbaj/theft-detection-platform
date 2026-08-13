"use client"

import { useQuery } from "@tanstack/react-query"
import { statsQueryKey } from "@/features/analytics/api/stats-key"
import type { Stats } from "@/features/analytics/schemas/stats"

export function StatsSummary() {
  const { data } = useQuery<Stats>({
    queryKey: statsQueryKey,
    queryFn: () => {
      throw new Error("stats are provided by the server")
    },
  })

  if (data === undefined) {
    return null
  }

  return (
    <dl className="grid grid-cols-3 gap-4 text-sm">
      <div>
        <dt className="text-muted-foreground">alerts today</dt>
        <dd className="text-2xl tabular-nums">{data.alerts_today}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">cameras</dt>
        <dd className="text-2xl tabular-nums">{data.total_cameras}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">high severity</dt>
        <dd className="text-2xl tabular-nums">{data.high_severity}</dd>
      </div>
    </dl>
  )
}
