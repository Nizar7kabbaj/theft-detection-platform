"use client"

import { useEffect, useState } from "react"
import type { AlertFilters } from "@/features/alerts/api/alert-keys"
import { useAlertPage } from "@/features/alerts/hooks/use-alert-page"
import { relativeAge } from "@/features/alerts/lib/format"
import type { Stats } from "@/features/analytics/schemas/stats"

const LABEL_CLASS = "font-mono text-[10px] text-muted-foreground uppercase tracking-wider"

const VALUE_CLASS = "font-mono text-2xl tabular-nums"

const CLOCK_INTERVAL_MS = 30_000

function Tile({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="flex flex-col gap-2 border-border border-r px-5 py-4 last:border-r-0">
      <span className={LABEL_CLASS}>{label}</span>
      <span className={`${VALUE_CLASS} ${tone}`}>{value}</span>
    </div>
  )
}

export function QueueSummary({ stats, filters }: { stats: Stats | null; filters: AlertFilters }) {
  const query = useAlertPage(filters)
  const [now, setNow] = useState<number | null>(null)

  useEffect(() => {
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), CLOCK_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [])

  const rows = query.data?.pages.flatMap((page) => page.items) ?? []
  const newest = rows.reduce<string | null>((latest, alert) => {
    if (latest === null || alert.occurred_at > latest) {
      return alert.occurred_at
    }
    return latest
  }, null)

  const lastEvent = newest === null || now === null ? "—" : relativeAge(newest, now)
  const high = stats === null ? null : stats.high_severity
  const medium = stats === null ? null : stats.medium_severity

  return (
    <div className="grid grid-cols-2 rounded-lg border border-border bg-card md:grid-cols-4">
      <Tile
        label="events today"
        tone="text-foreground"
        value={stats === null ? "—" : String(stats.alerts_today)}
      />
      <Tile
        label="high severity"
        tone={high !== null && high > 0 ? "text-destructive" : "text-foreground"}
        value={high === null ? "—" : String(high)}
      />
      <Tile
        label="medium severity"
        tone={medium !== null && medium > 0 ? "text-warning" : "text-foreground"}
        value={medium === null ? "—" : String(medium)}
      />
      <Tile label="last event" tone="text-foreground" value={lastEvent} />
    </div>
  )
}
