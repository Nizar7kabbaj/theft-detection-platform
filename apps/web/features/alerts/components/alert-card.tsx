"use client"

import type { Route } from "next"
import Link from "next/link"
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

const MONO_CLASS = "font-mono text-xs tabular-nums"

const FIELD_LABEL_CLASS = "font-mono text-[9px] text-muted-foreground uppercase tracking-wider"

export function AlertCard({
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
  const [frameFailed, setFrameFailed] = useState(false)
  const mutation = useAcknowledgeAlert(alert._id, filters)
  const href = `/alerts/${alert._id}` as Route

  const snapshot = alert.snapshot_url ?? null
  const showFrame = snapshot !== null && !frameFailed
  const percent =
    alert.confidence === null || alert.confidence === undefined
      ? null
      : Math.round(alert.confidence * 100)
  const decided = alert.decision !== "DECISION_UNSPECIFIED"

  return (
    <li className="flex flex-col gap-3 border-border border-b p-3 last:border-b-0">
      <div className="flex items-start justify-between gap-3">
        <span className={`flex items-center gap-2 ${SEVERITY_CLASS[alert.severity]}`}>
          <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
          <span className="font-mono text-[11px] uppercase tracking-wide">
            {SEVERITY_LABEL[alert.severity]}
          </span>
        </span>
        <span className="flex flex-col items-end gap-1">
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
      </div>

      <div className="flex items-start gap-3">
        {showFrame ? (
          <img
            alt={`frame from ${alert.camera_id}`}
            className="size-14 shrink-0 rounded-sm border border-border object-cover"
            decoding="async"
            height={56}
            loading="lazy"
            onError={() => setFrameFailed(true)}
            src={snapshot}
            width={56}
          />
        ) : (
          <span className="flex size-14 shrink-0 items-center justify-center rounded-sm border border-border border-dashed font-mono text-[9px] text-muted-foreground">
            no frame
          </span>
        )}
        <span className="flex min-w-0 flex-col gap-1">
          <Link
            className="text-foreground underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            href={href}
          >
            {alertTypeLabel(alert.alert_type)}
          </Link>
          <span className="truncate text-muted-foreground text-sm">
            {alert.object_name === "" ? "unidentified" : alert.object_name}
          </span>
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <span className="flex flex-col gap-0.5">
          <span className={FIELD_LABEL_CLASS}>camera</span>
          <span className={`${MONO_CLASS} text-foreground`}>{alert.camera_id}</span>
        </span>
        <span className="flex flex-col gap-0.5">
          <span className={FIELD_LABEL_CLASS}>occurred</span>
          <span className={`${MONO_CLASS} text-foreground`}>{clockTime(alert.occurred_at)}</span>
          <span className={`${MONO_CLASS} text-[10px] text-muted-foreground`}>
            {now === null ? "" : relativeAge(alert.occurred_at, now)}
          </span>
        </span>
        <span className="flex flex-col gap-0.5">
          <span className={FIELD_LABEL_CLASS}>confidence</span>
          <span className={`${MONO_CLASS} text-foreground`}>
            {percent === null ? "—" : `${percent}%`}
          </span>
        </span>
      </div>

      <span className={`${MONO_CLASS} text-[10px] text-muted-foreground`} title={alert.alert_id}>
        {shortAlertId(alert.alert_id)}
      </span>

      {canAcknowledge && !alert.acknowledged ? (
        <Button
          className="w-full"
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
          size="sm"
          variant="outline"
        >
          {mutation.isPending ? "sending" : "acknowledge"}
        </Button>
      ) : null}
    </li>
  )
}
