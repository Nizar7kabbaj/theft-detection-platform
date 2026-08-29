import { RankedList, type RankedRow } from "@/features/analytics/components/ranked-list"
import type { CameraTally, DurationSpread, TypeTally } from "@/features/analytics/schemas/breakdown"
import type { AlertBucket } from "@/features/analytics/schemas/timeseries"

const TYPE_LABEL: Record<string, string> = {
  ALERT_TYPE_CONCEALMENT: "concealment",
  ALERT_TYPE_LOITERING: "loitering",
  ALERT_TYPE_OBJECT_PROXIMITY: "object proximity",
  ALERT_TYPE_UNSPECIFIED: "unspecified",
}

const DURATION_ROWS: readonly (readonly [keyof DurationSpread, string])[] = [
  ["under_60", "under 1m"],
  ["under_300", "1 to 5m"],
  ["under_900", "5 to 15m"],
  ["over_900", "over 15m"],
]

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

export function DurationPanel({ duration }: { duration: DurationSpread }) {
  const rows: RankedRow[] = DURATION_ROWS.map(([field, label]) => ({
    key: field,
    label,
    count: duration[field],
    tone: "info",
    muted: false,
    note: null,
  }))
  return (
    <RankedList
      empty="no alert in this window was decided"
      eyebrow="review duration"
      rows={rows.some((row) => row.count > 0) ? rows : []}
      showShare={false}
      title="time to decision"
      total={sum(rows.map((row) => row.count))}
    />
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
    <RankedList
      empty="no alert in this window carries a behaviour class"
      eyebrow="behaviour ranking"
      rows={rows}
      showShare={true}
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
      note: offline.has(entry.camera_id) ? "offline" : null,
    }))
  return (
    <RankedList
      empty="no camera raised an alert in this window"
      eyebrow="camera workload"
      rows={rows}
      showShare={true}
      title="where review work starts"
      total={total}
    />
  )
}
