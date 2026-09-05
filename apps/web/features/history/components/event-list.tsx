"use client"

import { Clock, Download } from "lucide-react"
import type { Route } from "next"
import Link from "next/link"
import { useCallback, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { EmptyState } from "@/components/ui/empty-state"
import { buildCsv, downloadCsv } from "@/features/alerts/lib/export-csv"
import {
  alertTypeLabel,
  clockTime,
  DECISION_LABEL,
  formatTimestamp,
} from "@/features/alerts/lib/format"
import type { Alert, Decision } from "@/features/alerts/schemas/alert"

const DOT: Record<string, string> = {
  SEVERITY_CRITICAL: "bg-destructive",
  SEVERITY_WARNING: "bg-warning",
  SEVERITY_NOTICE: "bg-info",
  SEVERITY_INFO: "bg-muted-foreground/60",
  SEVERITY_UNSPECIFIED: "bg-muted-foreground/40",
}

const OUTCOME: Record<Decision, string> = {
  DECISION_UNSPECIFIED: "text-muted-foreground/70",
  DECISION_CONFIRMED: "text-destructive",
  DECISION_DISMISSED: "text-muted-foreground",
  DECISION_UNSURE: "text-warning",
}

const PILL = "rounded-sm px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide"
const DELIVERY_TONE: Record<string, string> = {
  sent: "text-success",
  buffered: "text-warning",
  pending: "text-muted-foreground",
  sending: "text-muted-foreground",
  failed: "text-destructive",
  dead: "text-destructive",
  unknown: "text-muted-foreground/60",
}

function deliveryLabel(alert: Alert): string {
  if (alert.dispatch_failed) {
    return "not queued"
  }
  if (alert.delivery === null || alert.delivery === undefined) {
    return "unknown"
  }
  return alert.delivery.known ? alert.delivery.state : "not seen"
}

function deliveryTone(alert: Alert): string {
  if (alert.dispatch_failed) {
    return "text-destructive"
  }
  const state = alert.delivery?.known === true ? alert.delivery.state : "unknown"
  return DELIVERY_TONE[state] ?? "text-muted-foreground/60"
}

function stateOf(alert: Alert): string {
  if (alert.decision !== "DECISION_UNSPECIFIED") {
    return "closed"
  }
  return alert.acknowledged ? "seen" : "open"
}

export function EventList({
  rows,
  cameraNames,
  children,
}: {
  rows: readonly Alert[]
  cameraNames: ReadonlyMap<string, string>
  children?: React.ReactNode
}) {
  const [term, setTerm] = useState("")

  const visible = useMemo(() => {
    const needle = term.trim().toLowerCase()
    if (needle === "") {
      return rows
    }
    return rows.filter((alert) => {
      const camera = cameraNames.get(alert.camera_id) ?? alert.camera_id
      return (
        camera.toLowerCase().includes(needle) ||
        alert.object_name.toLowerCase().includes(needle) ||
        alertTypeLabel(alert.alert_type).toLowerCase().includes(needle)
      )
    })
  }, [cameraNames, rows, term])

  const exportRows = useCallback(() => {
    const stamp = new Date().toISOString().slice(0, 19).replaceAll(":", "")
    downloadCsv(buildCsv(visible, cameraNames), `history-${stamp}.csv`)
  }, [cameraNames, visible])

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            chronological record
          </p>
          <h2 className="font-medium text-base text-foreground">events in sequence</h2>
          <p className="text-muted-foreground text-sm">
            past alerts and the decision taken on each
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="sr-only" htmlFor="row-filter">
            filter loaded rows
          </label>
          <input
            className="h-8 w-44 rounded-lg border border-border bg-background px-2 text-foreground text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            id="row-filter"
            onChange={(event) => setTerm(event.target.value)}
            placeholder="filter loaded rows"
            type="search"
            value={term}
          />
          <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
            {visible.length} loaded
          </span>
          <Button disabled={visible.length === 0} onClick={exportRows} size="xs" variant="ghost">
            <Download aria-hidden="true" className="size-3" />
            export loaded rows
          </Button>
        </div>
      </div>

      {visible.length === 0 ? (
        <EmptyState
          description="widen the range, clear a filter, or order by alert time"
          icon={Clock}
          title="no events in this window"
        />
      ) : (
        <ul className="flex flex-col">
          {visible.map((alert) => (
            <li className="border-border/60 border-b last:border-b-0" key={alert._id}>
              <Link
                className="flex items-center gap-4 rounded-md px-1 py-3 outline-none transition-colors duration-150 hover:bg-foreground/[0.03] focus-visible:ring-2 focus-visible:ring-ring"
                href={`/alerts/${alert._id}` as Route}
              >
                <span className="flex w-20 shrink-0 flex-col">
                  <span className="font-mono text-foreground text-sm tabular-nums">
                    {clockTime(alert.created_at)}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {formatTimestamp(alert.created_at)}
                  </span>
                </span>
                <span
                  className={`size-1.5 shrink-0 rounded-full ${DOT[alert.severity] ?? DOT.SEVERITY_UNSPECIFIED}`}
                />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate font-medium text-foreground text-sm">
                    {alertTypeLabel(alert.alert_type)}
                  </span>
                  <span className="truncate text-muted-foreground text-xs">
                    {cameraNames.get(alert.camera_id) ?? alert.camera_id}
                    {alert.object_name === "" ? "" : ` · ${alert.object_name}`}
                  </span>
                </span>
                <span className={`${PILL} shrink-0 bg-foreground/10 text-muted-foreground`}>
                  {stateOf(alert)}
                </span>
                <span
                  className={`w-24 shrink-0 text-right font-mono text-[11px] tracking-wide ${deliveryTone(alert)}`}
                >
                  {deliveryLabel(alert)}
                </span>
                <span
                  className={`w-24 shrink-0 text-right font-mono text-[11px] uppercase tracking-wide ${OUTCOME[alert.decision]}`}
                >
                  {DECISION_LABEL[alert.decision]}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {children}
    </Card>
  )
}
