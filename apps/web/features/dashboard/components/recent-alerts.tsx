import type { Route } from "next"
import Link from "next/link"
import { type AlertSeverity, EMPTY_FILTERS } from "@/features/alerts/api/alert-keys"
import { fetchAlertPage } from "@/features/alerts/api/alerts-server"
import type { Alert } from "@/features/alerts/schemas/alert"
import { cn } from "@/lib/utils"

const SEVERITY_LABEL: Record<Alert["severity"], string> = {
  SEVERITY_UNSPECIFIED: "unspecified",
  SEVERITY_INFO: "info",
  SEVERITY_NOTICE: "notice",
  SEVERITY_WARNING: "warning",
  SEVERITY_CRITICAL: "critical",
}

const SEVERITY_CHIP: Record<Alert["severity"], string> = {
  SEVERITY_UNSPECIFIED: "border-border text-muted-foreground",
  SEVERITY_INFO: "border-border text-muted-foreground",
  SEVERITY_NOTICE: "border-info/40 text-info",
  SEVERITY_WARNING: "border-warning/40 text-warning",
  SEVERITY_CRITICAL: "border-destructive/40 text-destructive",
}

const ROW_LIMIT = 6

function clockLabel(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return "--:--:--"
  }
  const hours = String(parsed.getUTCHours()).padStart(2, "0")
  const minutes = String(parsed.getUTCMinutes()).padStart(2, "0")
  const seconds = String(parsed.getUTCSeconds()).padStart(2, "0")
  return `${hours}:${minutes}:${seconds}`
}

export async function RecentAlerts({ severity }: { severity: AlertSeverity | null }) {
  let items: Alert[]
  try {
    const page = await fetchAlertPage({ ...EMPTY_FILTERS, severity }, null)
    items = page.items.slice(0, ROW_LIMIT)
  } catch {
    return <p className="font-mono text-[11px] text-muted-foreground">alerts are unavailable</p>
  }

  if (items.length === 0) {
    return (
      <p className="font-mono text-[11px] text-muted-foreground">no alerts match this filter</p>
    )
  }

  return (
    <ul className="flex flex-col">
      {items.map((alert) => (
        <li key={alert._id}>
          <Link
            href={`/alerts/${alert._id}` as Route}
            className="flex min-w-0 items-center gap-3 border-border border-b px-1 py-2.5 outline-none transition-colors last:border-b-0 hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span
              className={cn(
                "shrink-0 rounded-sm border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.06em]",
                SEVERITY_CHIP[alert.severity],
              )}
            >
              {SEVERITY_LABEL[alert.severity]}
            </span>
            <span className="shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
              {clockLabel(alert.occurred_at)}
            </span>
            <span className="min-w-0 shrink-0 truncate font-mono text-[11px] text-muted-foreground">
              {alert.camera_id}
            </span>
            <span className="min-w-0 flex-1 truncate text-[12px]">{alert.object_name}</span>
            <span
              className={cn(
                "ml-auto shrink-0 font-mono text-[9px] uppercase tracking-[0.04em]",
                alert.acknowledged ? "text-muted-foreground" : "text-warning",
              )}
            >
              {alert.acknowledged ? "reviewed" : "open"}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}
