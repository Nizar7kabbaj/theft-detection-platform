"use client"
import { useAlertDetail } from "@/features/alerts/hooks/use-alert-detail"
import { DECISION_LABEL } from "@/features/alerts/lib/format"
import type { AlertDetail } from "@/features/alerts/schemas/alert"

const CELL_CLASS = "flex flex-col gap-1"
const LABEL_CLASS = "font-mono text-[10px] text-muted-foreground uppercase tracking-[0.16em]"
const VALUE_CLASS = "font-mono text-foreground text-sm tabular-nums"

export function FactStrip({ alert }: { alert: AlertDetail }) {
  const { data } = useAlertDetail(alert._id, alert)
  const track = data.person?.track_id
  return (
    <dl className="grid grid-cols-2 gap-6 border-border border-y py-4 sm:grid-cols-4">
      <div className={CELL_CLASS}>
        <dt className={LABEL_CLASS}>camera</dt>
        <dd className={VALUE_CLASS}>{data.camera_id}</dd>
      </div>
      <div className={CELL_CLASS}>
        <dt className={LABEL_CLASS}>frame</dt>
        <dd className={VALUE_CLASS}>{data.frame_index}</dd>
      </div>
      <div className={CELL_CLASS}>
        <dt className={LABEL_CLASS}>person track</dt>
        <dd className={VALUE_CLASS}>
          {track === null || track === undefined ? "not tracked" : `#${track}`}
        </dd>
      </div>
      <div className={CELL_CLASS}>
        <dt className={LABEL_CLASS}>decision</dt>
        <dd className={VALUE_CLASS}>{DECISION_LABEL[data.decision]}</dd>
      </div>
    </dl>
  )
}
