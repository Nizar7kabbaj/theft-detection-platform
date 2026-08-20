import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { Stats } from "@/features/analytics/schemas/stats"

const VALUE_CLASS = "font-semibold text-2xl text-foreground tabular-nums"
const TERM_CLASS = "text-muted-foreground text-sm"

function topObjectLabel(stats: Stats): string {
  const first = stats.top_objects[0]
  if (first === undefined || first.object === null) {
    return "none recorded"
  }
  return `${first.object} (${first.count})`
}

export function StatsCards({ stats }: { stats: Stats }) {
  const entries = [
    { term: "alerts today", value: String(stats.alerts_today) },
    { term: "alerts total", value: String(stats.total_alerts) },
    { term: "high severity", value: String(stats.high_severity) },
    { term: "medium severity", value: String(stats.medium_severity) },
    { term: "detections", value: String(stats.total_detections) },
    { term: "cameras", value: String(stats.total_cameras) },
  ]
  return (
    <Card>
      <CardHeader>
        <CardTitle>current totals</CardTitle>
        <CardDescription>
          counted across the whole collection, most frequent object {topObjectLabel(stats)}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {entries.map((entry) => (
            <div className="flex flex-col gap-0.5" key={entry.term}>
              <dt className={TERM_CLASS}>{entry.term}</dt>
              <dd className={VALUE_CLASS}>{entry.value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
