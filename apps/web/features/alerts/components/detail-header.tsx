import {
  alertTypeLabel,
  DECISION_LABEL,
  formatTimestamp,
  objectLabel,
  SEVERITY_CLASS,
  SEVERITY_LABEL,
} from "@/features/alerts/lib/format"
import type { AlertDetail } from "@/features/alerts/schemas/alert"

const FIELD_CLASS = "flex flex-col gap-0.5"
const LABEL_CLASS = "text-muted-foreground text-xs"
const VALUE_CLASS = "text-foreground text-sm"

export function DetailHeader({ alert }: { alert: AlertDetail }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="font-semibold text-foreground text-xl tracking-tight">
          {alertTypeLabel(alert.alert_type)} — {objectLabel(alert)}
        </h1>
        <p className="text-muted-foreground text-sm">
          camera {alert.camera_id}, session {alert.session_id}, frame {alert.frame_index}
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className={FIELD_CLASS}>
          <dt className={LABEL_CLASS}>severity</dt>
          <dd className={`${VALUE_CLASS} ${SEVERITY_CLASS[alert.severity]}`}>
            {SEVERITY_LABEL[alert.severity]}
          </dd>
        </div>
        <div className={FIELD_CLASS}>
          <dt className={LABEL_CLASS}>occurred</dt>
          <dd className={`${VALUE_CLASS} tabular-nums`}>{formatTimestamp(alert.occurred_at)}</dd>
        </div>
        <div className={FIELD_CLASS}>
          <dt className={LABEL_CLASS}>acknowledged</dt>
          <dd className={VALUE_CLASS}>
            {alert.acknowledged
              ? alert.acknowledged_at === null || alert.acknowledged_at === undefined
                ? "yes"
                : formatTimestamp(alert.acknowledged_at)
              : "no"}
          </dd>
        </div>
        <div className={FIELD_CLASS}>
          <dt className={LABEL_CLASS}>decision</dt>
          <dd className={VALUE_CLASS}>{DECISION_LABEL[alert.decision]}</dd>
        </div>
      </dl>
    </div>
  )
}
