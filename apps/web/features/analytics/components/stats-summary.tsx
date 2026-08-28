"use client"
import { useQuery } from "@tanstack/react-query"
import { statsQueryKey } from "@/features/analytics/api/stats-key"
import type { Stats } from "@/features/analytics/schemas/stats"
import { cn } from "@/lib/utils"

const LABEL_CLASS =
  "font-mono text-[9px] text-muted-foreground uppercase leading-none tracking-[0.09em]"

const VALUE_CLASS = "mt-2 font-mono text-2xl leading-none tabular-nums"

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
    <dl className="grid grid-cols-3 gap-4">
      <div>
        <dt className={LABEL_CLASS}>alerts today</dt>
        <dd className={VALUE_CLASS}>{data.alerts_today}</dd>
      </div>
      <div>
        <dt className={LABEL_CLASS}>cameras</dt>
        <dd className={VALUE_CLASS}>{data.total_cameras}</dd>
      </div>
      <div>
        <dt className={LABEL_CLASS}>high severity</dt>
        <dd className={cn(VALUE_CLASS, data.high_severity > 0 && "text-destructive")}>
          {data.high_severity}
        </dd>
      </div>
    </dl>
  )
}
