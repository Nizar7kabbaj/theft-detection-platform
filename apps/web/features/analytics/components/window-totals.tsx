import type { AlertBucket, DecisionBucket } from "@/features/analytics/schemas/timeseries"

const TERM_CLASS = "text-muted-foreground text-xs"
const VALUE_CLASS = "font-semibold text-foreground text-lg tabular-nums"

function sum(values: readonly number[]): number {
  return values.reduce((total, value) => total + value, 0)
}

export function WindowTotals({
  alerts,
  decisions,
}: {
  alerts: readonly AlertBucket[]
  decisions: readonly DecisionBucket[]
}) {
  const entries = [
    { term: "alerts in window", value: sum(alerts.map((bucket) => bucket.total)) },
    { term: "critical", value: sum(alerts.map((bucket) => bucket.critical)) },
    { term: "warning", value: sum(alerts.map((bucket) => bucket.warning)) },
    { term: "decisions in window", value: sum(decisions.map((bucket) => bucket.total)) },
    { term: "confirmed", value: sum(decisions.map((bucket) => bucket.confirmed)) },
    { term: "dismissed", value: sum(decisions.map((bucket) => bucket.dismissed)) },
  ]
  return (
    <dl className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-xl px-4 py-3 ring-1 ring-foreground/10">
      {entries.map((entry) => (
        <div className="flex flex-col gap-0.5" key={entry.term}>
          <dt className={TERM_CLASS}>{entry.term}</dt>
          <dd className={VALUE_CLASS}>{entry.value}</dd>
        </div>
      ))}
      <p className="ml-auto text-muted-foreground text-xs">summed from the buckets shown below</p>
    </dl>
  )
}
