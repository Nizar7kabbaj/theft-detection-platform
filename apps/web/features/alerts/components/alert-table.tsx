"use client"

import { Download, ShieldAlert } from "lucide-react"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import type { AlertFilters } from "@/features/alerts/api/alert-keys"
import { AlertCard } from "@/features/alerts/components/alert-card"
import { AlertRow } from "@/features/alerts/components/alert-row"
import { NewAlertPill } from "@/features/alerts/components/new-alert-pill"
import { StreamIndicator } from "@/features/alerts/components/stream-indicator"
import { useAlertPage } from "@/features/alerts/hooks/use-alert-page"
import { useAlertSocket } from "@/features/alerts/hooks/use-alert-socket"
import { buildCsv, downloadCsv } from "@/features/alerts/lib/export-csv"
import type { Alert } from "@/features/alerts/schemas/alert"

const HEAD_CLASS =
  "px-3 py-2 text-left font-mono font-normal text-[10px] text-muted-foreground uppercase tracking-wider"

const CLOCK_INTERVAL_MS = 30_000

export function AlertTable({
  filters,
  canAcknowledge,
  text,
}: {
  filters: AlertFilters
  canAcknowledge: boolean
  text: string
}) {
  const query = useAlertPage(filters)
  const { pendingCount, clearPending } = useAlertSocket(filters)
  const [now, setNow] = useState<number | null>(null)

  useEffect(() => {
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), CLOCK_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [])

  const refresh = () => {
    clearPending()
    void query.refetch()
  }
  const exportRows = (items: readonly Alert[]) => {
    const stamp = new Date().toISOString().slice(0, 19).replaceAll(":", "")
    downloadCsv(buildCsv(items, new Map()), `alerts-${stamp}.csv`)
  }

  if (query.isPending) {
    return <p className="text-muted-foreground text-sm">loading alerts</p>
  }

  if (query.isError) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-destructive text-sm">alerts could not be loaded</p>
        <Button onClick={() => void query.refetch()} size="sm" variant="outline">
          try again
        </Button>
      </div>
    )
  }

  const needle = text.trim().toLowerCase()
  const loaded = query.data.pages.flatMap((page) => page.items)
  const rows =
    needle === ""
      ? loaded
      : loaded.filter((alert) =>
          [alert.alert_id, alert.camera_id, alert.object_name, alert.severity]
            .join(" ")
            .toLowerCase()
            .includes(needle),
        )

  if (rows.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <NewAlertPill count={pendingCount} onRefresh={refresh} />
        <EmptyState
          icon={ShieldAlert}
          title="no events match these filters"
          description="clear the filters or wait for the edge to escalate an event"
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <NewAlertPill count={pendingCount} onRefresh={refresh} />
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <ul className="flex flex-col md:hidden">
          {rows.map((alert) => (
            <AlertCard
              alert={alert}
              canAcknowledge={canAcknowledge}
              filters={filters}
              key={alert._id}
              now={now}
            />
          ))}
        </ul>
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">events escalated for human review</caption>
            <thead className="border-border border-b">
              <tr>
                <th className={HEAD_CLASS} scope="col">
                  evidence
                </th>
                <th className={HEAD_CLASS} scope="col">
                  severity
                </th>
                <th className={HEAD_CLASS} scope="col">
                  event
                </th>
                <th className={HEAD_CLASS} scope="col">
                  object
                </th>
                <th className={HEAD_CLASS} scope="col">
                  camera
                </th>
                <th className={HEAD_CLASS} scope="col">
                  confidence
                </th>
                <th className={HEAD_CLASS} scope="col">
                  occurred
                </th>
                <th className={HEAD_CLASS} scope="col">
                  state
                </th>
                <th className={`${HEAD_CLASS} text-right`} scope="col">
                  actions
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((alert) => (
                <AlertRow
                  alert={alert}
                  canAcknowledge={canAcknowledge}
                  filters={filters}
                  key={alert._id}
                  now={now}
                />
              ))}
            </tbody>
          </table>
        </div>
        <div className="grid grid-cols-3 items-center gap-3 border-border border-t px-3 py-2">
          <StreamIndicator />
          {query.hasNextPage ? (
            <Button
              className="justify-self-center"
              disabled={query.isFetchingNextPage}
              onClick={() => void query.fetchNextPage()}
              size="sm"
              variant="outline"
            >
              {query.isFetchingNextPage ? "loading" : "load more"}
            </Button>
          ) : (
            <span />
          )}
          <span className="flex items-center justify-end gap-3">
            <span className="font-mono text-[10px] text-muted-foreground tabular-nums">
              {rows.length === 1 ? "1 event loaded" : `${rows.length} events loaded`}
            </span>
            <Button onClick={() => exportRows(rows)} size="xs" variant="ghost">
              <Download aria-hidden="true" className="size-3" />
              export
            </Button>
          </span>
        </div>
      </div>
    </div>
  )
}
