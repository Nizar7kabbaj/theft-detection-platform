import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { Stats } from "@/features/analytics/schemas/stats"

type TopObject = Stats["top_objects"][number]

const ROW_CLASS = "flex items-center gap-3"
const NAME_CLASS = "w-32 shrink-0 truncate text-sm"
const TRACK_CLASS = "h-2 flex-1 overflow-hidden rounded-full bg-muted"
const BAR_CLASS = "h-full rounded-full bg-chart-1"
const COUNT_CLASS = "w-10 shrink-0 text-right text-sm tabular-nums"

export function TopObjects({ objects }: { objects: readonly TopObject[] }) {
  const named = objects.filter((entry) => entry.object !== null && entry.object !== "")
  if (named.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>objects seen</CardTitle>
          <CardDescription>no alert carries a recognised object class yet</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  const highest = Math.max(...named.map((entry) => entry.count))
  return (
    <Card>
      <CardHeader>
        <CardTitle>objects seen</CardTitle>
        <CardDescription>
          most frequent object classes across every alert on record, bar width relative to the
          highest count
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="flex flex-col gap-3">
          {named.map((entry) => (
            <div className={ROW_CLASS} key={entry.object}>
              <dt className={NAME_CLASS}>{entry.object}</dt>
              <div aria-hidden="true" className={TRACK_CLASS}>
                <div
                  className={BAR_CLASS}
                  style={{ width: `${Math.round((entry.count / highest) * 100)}%` }}
                />
              </div>
              <dd className={COUNT_CLASS}>{entry.count}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
