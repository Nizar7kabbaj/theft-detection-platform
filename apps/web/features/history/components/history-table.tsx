import { Clock } from "lucide-react"
import type { Route } from "next"
import Link from "next/link"
import { EmptyState } from "@/components/ui/empty-state"
import {
  DECISION_LABEL,
  formatTimestamp,
  SEVERITY_CLASS,
  SEVERITY_LABEL,
} from "@/features/alerts/lib/format"
import type { Alert, Decision } from "@/features/alerts/schemas/alert"
import type { AlertSort } from "@/features/history/api/history-keys"

const HEAD_CLASS = "px-3 py-2 text-left font-medium text-muted-foreground"
const CELL_CLASS = "px-3 py-2 align-middle"
const LINK_CLASS =
  "rounded-sm underline-offset-4 outline-none transition-colors duration-150 hover:underline focus-visible:ring-2 focus-visible:ring-ring"

const DECISION_CLASS: Record<Decision, string> = {
  DECISION_UNSPECIFIED: "text-muted-foreground",
  DECISION_CONFIRMED: "text-destructive",
  DECISION_DISMISSED: "text-muted-foreground",
  DECISION_UNSURE: "text-warning",
}

function decidedCell(alert: Alert): string {
  if (alert.decided_at === null || alert.decided_at === undefined) {
    return "—"
  }
  return formatTimestamp(alert.decided_at)
}

function reviewerCell(alert: Alert): string {
  if (alert.decided_by === null || alert.decided_by === undefined || alert.decided_by === "") {
    return "—"
  }
  return alert.decided_by
}

export function HistoryTable({
  rows,
  sort,
  cameraNames,
}: {
  rows: readonly Alert[]
  sort: AlertSort
  cameraNames: ReadonlyMap<string, string>
}) {
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={Clock}
        title="no reviewed alerts match"
        description="clear the filters, or order by alert time to see alerts still waiting on a reviewer"
      />
    )
  }
  return (
    <div className="overflow-x-auto rounded-xl ring-1 ring-foreground/10">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">
          reviewed alerts ordered by {sort === "decided_at" ? "decision time" : "alert time"}, all
          times in UTC
        </caption>
        <thead className="border-border border-b bg-muted/40">
          <tr>
            <th className={HEAD_CLASS} scope="col">
              alert time
            </th>
            <th className={HEAD_CLASS} scope="col">
              decided
            </th>
            <th className={HEAD_CLASS} scope="col">
              reviewer
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
              outcome
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((alert) => (
            <tr
              className="border-border border-b transition-colors duration-150 last:border-b-0 hover:bg-muted/40"
              key={alert._id}
            >
              <td className={`${CELL_CLASS} whitespace-nowrap tabular-nums`}>
                <Link className={LINK_CLASS} href={`/alerts/${alert._id}` as Route}>
                  {formatTimestamp(alert.created_at)}
                </Link>
              </td>
              <td className={`${CELL_CLASS} whitespace-nowrap tabular-nums text-muted-foreground`}>
                {decidedCell(alert)}
              </td>
              <td className={CELL_CLASS}>{reviewerCell(alert)}</td>
              <td className={CELL_CLASS}>{cameraNames.get(alert.camera_id) ?? alert.camera_id}</td>
              <td className={`${CELL_CLASS} ${SEVERITY_CLASS[alert.severity]}`}>
                {SEVERITY_LABEL[alert.severity]}
              </td>
              <td className={CELL_CLASS}>{alert.object_name}</td>
              <td className={`${CELL_CLASS} ${DECISION_CLASS[alert.decision]}`}>
                {DECISION_LABEL[alert.decision]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
