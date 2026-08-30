import type { ReactNode } from "react"
import {
  alertTypeLabel,
  formatTimestamp,
  SEVERITY_CLASS,
  SEVERITY_LABEL,
  shortAlertId,
} from "@/features/alerts/lib/format"
import type { AlertDetail } from "@/features/alerts/schemas/alert"

const META_CLASS = "font-mono text-[11px] text-muted-foreground uppercase tracking-[0.14em]"
const CHIP_CLASS =
  "inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em]"

export function DetailHeader({ action, alert }: { action?: ReactNode; alert: AlertDetail }) {
  return (
    <div className="flex flex-col gap-3">
      <p className={META_CLASS}>
        alert {shortAlertId(alert.alert_id)} · session {alert.session_id} · frame{" "}
        {alert.frame_index}
      </p>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <h2 className="font-semibold text-3xl text-foreground text-balance tracking-tight">
            {alertTypeLabel(alert.alert_type)}
          </h2>
          <p className="font-mono text-muted-foreground text-xs">
            {alert.camera_id} · occurred {formatTimestamp(alert.occurred_at)} utc
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`${CHIP_CLASS} ${SEVERITY_CLASS[alert.severity]}`}>
            <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
            {SEVERITY_LABEL[alert.severity]}
          </span>
          {action}
        </div>
      </div>
    </div>
  )
}
