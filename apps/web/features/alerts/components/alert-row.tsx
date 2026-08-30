"use client"

import { ChevronRight } from "lucide-react"
import type { Route } from "next"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { AlertFilters } from "@/features/alerts/api/alert-keys"
import { useAcknowledgeAlert } from "@/features/alerts/hooks/use-acknowledge-alert"
import {
  alertTypeLabel,
  clockTime,
  DECISION_LABEL,
  relativeAge,
  SEVERITY_CLASS,
  SEVERITY_LABEL,
  shortAlertId,
} from "@/features/alerts/lib/format"
import type { Alert } from "@/features/alerts/schemas/alert"

const CELL_CLASS = "px-3 py-2.5 align-middle"

const MONO_CLASS = "font-mono text-xs tabular-nums"

const BAR_WIDTH: Record<number, string> = {
  0: "w-0",
  10: "w-[10%]",
  20: "w-[20%]",
  30: "w-[30%]",
  40: "w-[40%]",
  50: "w-[50%]",
  60: "w-[60%]",
  70: "w-[70%]",
  80: "w-[80%]",
  90: "w-[90%]",
  100: "w-full",
}

export function AlertRow({
  alert,
  filters,
  canAcknowledge,
  now,
}: {
  alert: Alert
  filters: AlertFilters
  canAcknowledge: boolean
  now: number | null
}) {
  const router = useRouter()
  const [frameFailed, setFrameFailed] = useState(false)
  const mutation = useAcknowledgeAlert(alert._id, filters)
  const href = `/alerts/${alert._id}` as Route

  const openDetail = () => {
    const selection = window.getSelection()
    if (selection !== null && selection.toString().length > 0) {
      return
    }
    router.push(href)
  }

  const snapshot = alert.snapshot_url ?? null
  const showFrame = snapshot !== null && !frameFailed
  const percent =
    alert.confidence === null || alert.confidence === undefined
      ? null
      : Math.round(alert.confidence * 100)
  const bucket = percent === null ? 0 : Math.round(percent / 10) * 10
  const decided = alert.decision !== "DECISION_UNSPECIFIED"
  const actionVisible = mutation.isPending ? "opacity-100" : "opacity-0"

  return (
    <tr
      className="group/row cursor-pointer border-border border-b transition-colors last:border-b-0 hover:bg-muted/30"
      onClick={openDetail}
    >
      <td className={CELL_CLASS}>
        {showFrame ? (
          <img
            alt={`frame from ${alert.camera_id}`}
            className="h-10 w-16 rounded-sm border border-border object-cover"
            decoding="async"
            height={40}
            loading="lazy"
            onError={() => setFrameFailed(true)}
            src={snapshot}
            width={64}
          />
        ) : (
          <span className="flex h-10 w-16 items-center justify-center rounded-sm border border-border border-dashed font-mono text-[9px] text-muted-foreground">
            no frame
          </span>
        )}
      </td>

      <td className={`${CELL_CLASS} ${SEVERITY_CLASS[alert.severity]}`}>
        <span className="flex items-center gap-2">
          <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
          <span className="font-mono text-[11px] uppercase tracking-wide">
            {SEVERITY_LABEL[alert.severity]}
          </span>
        </span>
      </td>

      <td className={CELL_CLASS}>
        <span className="flex flex-col gap-0.5">
          <Link
            className="text-foreground underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            href={href}
            onClick={(event) => event.stopPropagation()}
          >
            {alertTypeLabel(alert.alert_type)}
          </Link>
          <span
            className={`${MONO_CLASS} text-[10px] text-muted-foreground`}
            title={alert.alert_id}
          >
            {shortAlertId(alert.alert_id)}
          </span>
        </span>
      </td>

      <td className={CELL_CLASS}>
        {alert.object_name === "" ? (
          <span className="text-muted-foreground">unidentified</span>
        ) : (
          alert.object_name
        )}
      </td>

      <td className={`${CELL_CLASS} ${MONO_CLASS} text-muted-foreground`}>{alert.camera_id}</td>

      <td className={CELL_CLASS}>
        {percent === null ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <span className="flex w-16 flex-col gap-1">
            <span className={`${MONO_CLASS} text-foreground`}>{percent}%</span>
            <span className="h-0.5 w-full overflow-hidden rounded-full bg-muted">
              <span className={`block h-full bg-muted-foreground/70 ${BAR_WIDTH[bucket]}`} />
            </span>
          </span>
        )}
      </td>

      <td className={CELL_CLASS}>
        <span className="flex flex-col gap-0.5">
          <span className={`${MONO_CLASS} text-foreground`}>{clockTime(alert.occurred_at)}</span>
          <span className={`${MONO_CLASS} text-[10px] text-muted-foreground`}>
            {now === null ? "" : relativeAge(alert.occurred_at, now)}
          </span>
        </span>
      </td>

      <td className={CELL_CLASS}>
        <span className="flex flex-col items-start gap-1">
          <span
            className={
              alert.acknowledged
                ? "rounded-sm border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground uppercase tracking-wide"
                : "rounded-sm border border-warning/40 px-1.5 py-0.5 font-mono text-[10px] text-warning uppercase tracking-wide"
            }
          >
            {alert.acknowledged ? "acknowledged" : "open"}
          </span>
          {decided ? (
            <span className={`${MONO_CLASS} text-[10px] text-muted-foreground`}>
              {DECISION_LABEL[alert.decision]}
            </span>
          ) : null}
        </span>
      </td>

      <td className={`${CELL_CLASS} text-right`}>
        {canAcknowledge && !alert.acknowledged ? (
          <Button
            className={`${actionVisible} transition-opacity focus-visible:opacity-100 group-hover/row:opacity-100`}
            disabled={mutation.isPending}
            onClick={(event) => {
              event.stopPropagation()
              mutation.mutate()
            }}
            size="xs"
            variant="outline"
          >
            {mutation.isPending ? "sending" : "acknowledge"}
          </Button>
        ) : (
          <Link
            className="inline-flex items-center gap-1 rounded-sm font-mono text-[11px] text-muted-foreground uppercase tracking-wide opacity-0 transition-opacity focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none group-hover/row:opacity-100"
            href={href}
            onClick={(event) => event.stopPropagation()}
          >
            open
            <ChevronRight aria-hidden="true" className="size-3" />
          </Link>
        )}
      </td>
    </tr>
  )
}
