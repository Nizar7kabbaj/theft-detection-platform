import { Card } from "@/components/ui/card"
import { DurationDonutLazy } from "@/features/analytics/components/analytics-charts-lazy"
import { LaneList } from "@/features/analytics/components/lane-list"
import { RankedList, type RankedRow } from "@/features/analytics/components/ranked-list"
import { DURATION_BUCKETS, formatDuration } from "@/features/analytics/lib/duration-buckets"
import type { CameraTally, DurationSpread, TypeTally } from "@/features/analytics/schemas/breakdown"
import type { AlertBucket } from "@/features/analytics/schemas/timeseries"

const EYEBROW = "font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
const DURATION_CHIP =
  "inline-flex h-7 items-center gap-2 rounded-sm border border-border px-2.5 font-mono text-[10px] uppercase tracking-wide"

const TYPE_LABEL: Record<string, string> = {
  ALERT_TYPE_CONCEALMENT: "concealment",
  ALERT_TYPE_LOITERING: "loitering",
  ALERT_TYPE_OBJECT_PROXIMITY: "object proximity",
  ALERT_TYPE_UNSPECIFIED: "unspecified",
}

const SEVERITY_ROWS: readonly (readonly [
  Exclude<keyof AlertBucket, "bucket" | "total">,
  string,
  RankedRow["tone"],
])[] = [
  ["critical", "critical", "critical"],
  ["warning", "warning", "warning"],
  ["notice", "notice", "info"],
  ["info", "info", "neutral"],
  ["unspecified", "unspecified", "neutral"],
]

function sum(values: readonly number[]): number {
  return values.reduce((total, value) => total + value, 0)
}

function cameraNote(
  cameraId: string,
  names: ReadonlyMap<string, string>,
  offline: ReadonlySet<string>,
): string {
  const parts: string[] = []
  if (names.has(cameraId)) {
    parts.push(cameraId)
  } else {
    parts.push("not registered")
  }
  if (offline.has(cameraId)) {
    parts.push("offline")
  }
  return parts.join(" · ")
}

export function SeverityPanel({ alerts }: { alerts: readonly AlertBucket[] }) {
  const rows: RankedRow[] = SEVERITY_ROWS.map(([field, label, tone]) => ({
    key: field,
    label,
    count: sum(alerts.map((bucket) => bucket[field])),
    tone,
    muted: false,
    note: null,
  })).filter((row) => row.count > 0)
  return (
    <RankedList
      empty="no alerts were raised in this window"
      eyebrow="severity spread"
      rows={rows}
      showShare={false}
      title="events by level"
      total={sum(rows.map((row) => row.count))}
    />
  )
}

export function DurationPanel({
  decided,
  duration,
  median,
}: {
  decided: number
  duration: DurationSpread
  median: number | null
}) {
  return (
    <Card className="gap-5 p-5">
      <div className="flex flex-col gap-1">
        <p className={EYEBROW}>review duration</p>
        <div className="flex items-center gap-2">
          <h2 className="font-medium text-base text-foreground">time to decision</h2>
          {median === null ? null : (
            <span className="rounded-sm border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground uppercase tracking-wide tabular-nums">
              median {formatDuration(median)}
            </span>
          )}
        </div>
      </div>
      {decided === 0 ? (
        <p className="py-10 text-center text-muted-foreground text-xs">
          no alert in this window was decided
        </p>
      ) : (
        <>
          <DurationDonutLazy duration={duration} />
          <ul className="flex flex-wrap gap-2">
            {DURATION_BUCKETS.map((bucket) => (
              <li
                className={
                  duration[bucket.field] > 0
                    ? `${DURATION_CHIP} bg-accent text-foreground`
                    : `${DURATION_CHIP} text-muted-foreground opacity-50`
                }
                key={bucket.field}
              >
                <span aria-hidden="true" className={`size-2 shrink-0 rounded-full ${bucket.dot}`} />
                {bucket.label}
                <span className="text-foreground tabular-nums">{duration[bucket.field]}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="text-[11px] text-muted-foreground">
        {decided} decided in this window, time counted from raise to decision
      </p>
    </Card>
  )
}

export function BehaviourPanel({ types }: { types: readonly TypeTally[] }) {
  const total = sum(types.map((entry) => entry.count))
  const rows: RankedRow[] = [...types]
    .sort((left, right) => right.count - left.count)
    .map((entry) => ({
      key: entry.alert_type,
      label: TYPE_LABEL[entry.alert_type] ?? entry.alert_type.toLowerCase(),
      count: entry.count,
      tone: entry.alert_type === "ALERT_TYPE_CONCEALMENT" ? "critical" : "neutral",
      muted: false,
      note: null,
    }))
  return (
    <LaneList
      empty="no alert in this window carries a behaviour class"
      eyebrow="behaviour ranking"
      rows={rows}
      title="what triggered the alert"
      total={total}
    />
  )
}

export function CameraPanel({
  cameras,
  names,
  offline,
}: {
  cameras: readonly CameraTally[]
  names: ReadonlyMap<string, string>
  offline: ReadonlySet<string>
}) {
  const total = sum(cameras.map((entry) => entry.count))
  const rows: RankedRow[] = [...cameras]
    .sort((left, right) => right.count - left.count)
    .map((entry) => ({
      key: entry.camera_id,
      label: names.get(entry.camera_id) ?? entry.camera_id,
      count: entry.count,
      tone: "info",
      muted: offline.has(entry.camera_id),
      note: cameraNote(entry.camera_id, names, offline),
    }))
  return (
    <LaneList
      empty="no camera raised an alert in this window"
      eyebrow="camera workload"
      rows={rows}
      title="where review work starts"
      total={total}
    />
  )
}
