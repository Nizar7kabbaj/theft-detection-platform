import { Card } from "@/components/ui/card"
import type { StatsBreakdown } from "@/features/analytics/schemas/breakdown"
import type { AlertBucket } from "@/features/analytics/schemas/timeseries"

const EYEBROW = "font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
const VALUE = "font-mono text-3xl text-foreground leading-none tabular-nums"
const FOOT = "text-muted-foreground text-[11px] leading-[1.45]"
const ABSENT = "—"
const TERMS = [
  "alerts in range",
  "critical share",
  "decided share",
  "median time to decision",
] as const

function sum(values: readonly number[]): number {
  return values.reduce((total, value) => total + value, 0)
}

function percent(part: number, whole: number): string {
  if (whole <= 0) {
    return "0%"
  }
  return `${(Math.round((part / whole) * 1000) / 10).toFixed(1)}%`
}

function clock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(whole / 60)
  const rest = whole % 60
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`
}

type Tile = {
  term: string
  value: string
  foot: string
  alarm: boolean
}

function tiles(alerts: readonly AlertBucket[], breakdown: StatsBreakdown | null): readonly Tile[] {
  const raised = sum(alerts.map((bucket) => bucket.total))
  const critical = sum(alerts.map((bucket) => bucket.critical))
  const median = breakdown?.median_decision_seconds ?? null
  if (raised === 0) {
    return TERMS.map((term) => ({
      term,
      value: ABSENT,
      foot: "no alerts in this window",
      alarm: false,
    }))
  }
  return [
    {
      term: "alerts in range",
      value: String(raised),
      foot: "raised inside the window",
      alarm: false,
    },
    {
      term: "critical share",
      value: percent(critical, raised),
      foot: `${critical} critical of ${raised}`,
      alarm: critical > 0,
    },
    {
      term: "decided share",
      value: breakdown === null ? ABSENT : percent(breakdown.decided, breakdown.raised),
      foot:
        breakdown === null
          ? "needs the breakdown aggregation"
          : `${breakdown.decided} of ${breakdown.raised} raised in window were decided`,
      alarm: false,
    },
    {
      term: "median time to decision",
      value: median === null ? ABSENT : clock(median),
      foot:
        breakdown === null
          ? "needs the breakdown aggregation"
          : median === null
            ? "no alert in this window was decided"
            : "measured on decided alerts only",
      alarm: false,
    },
  ]
}

export function MetricTiles({
  alerts,
  breakdown,
}: {
  alerts: readonly AlertBucket[]
  breakdown: StatsBreakdown | null
}) {
  return (
    <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {tiles(alerts, breakdown).map((tile) => (
        <Card className="gap-3 p-5" key={tile.term}>
          <dt className={EYEBROW}>{tile.term}</dt>
          <dd className="flex flex-col gap-2">
            <span className={tile.alarm ? `${VALUE} text-destructive` : VALUE}>{tile.value}</span>
            <span className={FOOT}>{tile.foot}</span>
          </dd>
        </Card>
      ))}
    </dl>
  )
}
