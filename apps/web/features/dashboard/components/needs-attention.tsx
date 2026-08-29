import { ArrowUpRight, CameraOff, ShieldAlert, SignalLow } from "lucide-react"
import type { Route } from "next"
import Link from "next/link"
import type { ReactNode } from "react"
import { EMPTY_FILTERS } from "@/features/alerts/api/alert-keys"
import { fetchAlertPage } from "@/features/alerts/api/alerts-server"
import { fetchCameras } from "@/features/cameras/api/cameras-server"
import { cameraHealth } from "@/features/cameras/schemas/camera"
import { cn } from "@/lib/utils"

type Rank = "critical" | "warning"

type Item = {
  key: string
  rank: Rank
  icon: ReactNode
  title: string
  detail: string
  href: Route
  action: string
}

const BAR: Record<Rank, string> = {
  critical: "bg-destructive",
  warning: "bg-warning",
}

const ICON_TONE: Record<Rank, string> = {
  critical: "text-destructive",
  warning: "text-warning",
}

const MAX_ITEMS = 6

const NOT_WATCHED = "not watched yet: frame rate, stream latency, edge temperature, storage"

function occurredLabel(iso: string): string {
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) {
    return "time unknown"
  }
  const hours = String(parsed.getUTCHours()).padStart(2, "0")
  const minutes = String(parsed.getUTCMinutes()).padStart(2, "0")
  const seconds = String(parsed.getUTCSeconds()).padStart(2, "0")
  return `${hours}:${minutes}:${seconds} utc`
}

function ageLabel(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return "no frame recorded"
  }
  const whole = Math.max(0, Math.round(seconds))
  if (whole < 60) {
    return `last frame ${whole}s ago`
  }
  const minutes = Math.floor(whole / 60)
  if (minutes < 60) {
    return `last frame ${minutes}m ago`
  }
  return `last frame ${Math.floor(minutes / 60)}h ago`
}

async function collect(): Promise<Item[] | null> {
  const [cameras, alerts] = await Promise.all([
    fetchCameras().catch(() => null),
    fetchAlertPage({ ...EMPTY_FILTERS, acknowledged: false }, null).catch(() => null),
  ])

  if (cameras === null && alerts === null) {
    return null
  }

  const offline: Item[] = []
  const degraded: Item[] = []

  for (const camera of cameras ?? []) {
    const health = cameraHealth(camera)
    const href = `/cameras?id=${encodeURIComponent(camera.camera_id)}` as Route
    if (health.state === "offline") {
      offline.push({
        key: `camera-${camera.camera_id}`,
        rank: "critical",
        icon: <CameraOff aria-hidden="true" className="size-4" />,
        title: `${camera.name} is offline`,
        detail: `${camera.location} · ${ageLabel(health.age_seconds)}`,
        href,
        action: "open camera",
      })
    } else if (health.state === "degraded") {
      degraded.push({
        key: `camera-${camera.camera_id}`,
        rank: "warning",
        icon: <SignalLow aria-hidden="true" className="size-4" />,
        title: `${camera.name} frames are delayed`,
        detail: `${camera.location} · ${ageLabel(health.age_seconds)}`,
        href,
        action: "open camera",
      })
    }
  }

  const critical: Item[] = []
  const warning: Item[] = []

  for (const alert of alerts?.items ?? []) {
    if (alert.severity !== "SEVERITY_CRITICAL" && alert.severity !== "SEVERITY_WARNING") {
      continue
    }
    const rank: Rank = alert.severity === "SEVERITY_CRITICAL" ? "critical" : "warning"
    const item: Item = {
      key: `alert-${alert._id}`,
      rank,
      icon: <ShieldAlert aria-hidden="true" className="size-4" />,
      title: rank === "critical" ? "critical event unreviewed" : "warning event unreviewed",
      detail: `${alert.camera_id} · ${alert.object_name} · ${occurredLabel(alert.occurred_at)}`,
      href: `/alerts/${encodeURIComponent(alert._id)}` as Route,
      action: "review alert",
    }
    if (rank === "critical") {
      critical.push(item)
    } else {
      warning.push(item)
    }
  }

  return [...offline, ...critical, ...degraded, ...warning].slice(0, MAX_ITEMS)
}

function Row({ item }: { item: Item }) {
  return (
    <Link
      href={item.href}
      className="group flex min-w-0 items-center gap-3 overflow-hidden rounded-md border border-border bg-secondary/40 pr-3 outline-none transition-colors hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span aria-hidden="true" className={cn("h-full w-0.5 self-stretch", BAR[item.rank])} />
      <span aria-hidden="true" className={cn("shrink-0 py-3", ICON_TONE[item.rank])}>
        {item.icon}
      </span>
      <span className="flex min-w-0 flex-col gap-1 py-3">
        <span className="truncate font-medium text-[13px] leading-none">{item.title}</span>
        <span className="truncate font-mono text-[10px] text-muted-foreground leading-none">
          {item.detail}
        </span>
      </span>
      <span className="ml-auto flex shrink-0 items-center gap-1 font-mono text-[9px] text-muted-foreground uppercase tracking-[0.04em] transition-colors group-hover:text-foreground">
        {item.action}
        <ArrowUpRight aria-hidden="true" className="size-3" />
      </span>
    </Link>
  )
}

export async function NeedsAttention() {
  const items = await collect()

  if (items === null) {
    return (
      <p className="font-mono text-[11px] text-muted-foreground">
        queue unavailable, cameras and alerts could not be read
      </p>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <p className="font-mono text-[11px] text-success">nothing needs attention</p>
        <p className="font-mono text-[10px] text-muted-foreground">{NOT_WATCHED}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <Row item={item} key={item.key} />
        ))}
      </div>
      <p className="font-mono text-[10px] text-muted-foreground">{NOT_WATCHED}</p>
    </div>
  )
}
