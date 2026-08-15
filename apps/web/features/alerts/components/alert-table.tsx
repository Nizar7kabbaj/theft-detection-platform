"use client"
import { ShieldAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/ui/empty-state"
import type { AlertFilters } from "@/features/alerts/api/alert-keys"
import { AlertRow } from "@/features/alerts/components/alert-row"
import { NewAlertPill } from "@/features/alerts/components/new-alert-pill"
import { useAlertPage } from "@/features/alerts/hooks/use-alert-page"
import { useAlertSocket } from "@/features/alerts/hooks/use-alert-socket"

const HEAD_CLASS = "px-3 py-2 text-left font-medium text-muted-foreground"

export function AlertTable({
  filters,
  canAcknowledge,
}: {
  filters: AlertFilters
  canAcknowledge: boolean
}) {
  const query = useAlertPage(filters)
  const { pendingCount, clearPending } = useAlertSocket(filters)

  const refresh = () => {
    clearPending()
    void query.refetch()
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

  const rows = query.data.pages.flatMap((page) => page.items)

  if (rows.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <NewAlertPill count={pendingCount} onRefresh={refresh} />
        <EmptyState
          icon={ShieldAlert}
          title="no alerts match"
          description="clear the filters or wait for the pipeline to escalate an event"
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <NewAlertPill count={pendingCount} onRefresh={refresh} />
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">alerts escalated for human review</caption>
          <thead className="border-border border-b bg-muted/40">
            <tr>
              <th className={HEAD_CLASS} scope="col">
                time
              </th>
              <th className={HEAD_CLASS} scope="col">
                camera
              </th>
              <th className={HEAD_CLASS} scope="col">
                severity
              </th>
              <th className={HEAD_CLASS} scope="col">
                object
              </th>
              <th className={HEAD_CLASS} scope="col">
                confidence
              </th>
              <th className={HEAD_CLASS} scope="col">
                state
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
              />
            ))}
          </tbody>
        </table>
      </div>
      {query.hasNextPage ? (
        <Button
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
          size="sm"
          variant="outline"
        >
          {query.isFetchingNextPage ? "loading" : "load more"}
        </Button>
      ) : null}
    </div>
  )
}
