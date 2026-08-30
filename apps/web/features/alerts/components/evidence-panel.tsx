import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { alertTypeLabel } from "@/features/alerts/lib/format"
import type { AlertDetail, Concealment } from "@/features/alerts/schemas/alert"

const LABEL_CLASS = "font-mono text-[10px] text-muted-foreground uppercase tracking-[0.16em]"
const VALUE_CLASS = "font-mono text-foreground text-sm tabular-nums"

export function EvidencePanel({
  alertType,
  concealment,
}: {
  alertType: AlertDetail["alert_type"]
  concealment: Concealment | null | undefined
}) {
  return (
    <Card>
      <CardHeader>
        <p className={LABEL_CLASS}>rule evidence</p>
        <CardTitle className="text-lg">possible {alertTypeLabel(alertType)}</CardTitle>
        <CardDescription>
          {concealment === null || concealment === undefined
            ? "no concealment record was stored for this alert"
            : "the object left view while a wrist was close enough to have taken it"}
        </CardDescription>
      </CardHeader>
      {concealment === null || concealment === undefined ? null : (
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            <div className="flex flex-col gap-1">
              <dt className={LABEL_CLASS}>object missing</dt>
              <dd className={VALUE_CLASS}>{concealment.missing_frames} frames</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className={LABEL_CLASS}>last seen</dt>
              <dd className={VALUE_CLASS}>frame {concealment.last_seen_frame}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className={LABEL_CLASS}>grab distance</dt>
              <dd className={VALUE_CLASS}>{concealment.grab_distance.toFixed(2)} torso lengths</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className={LABEL_CLASS}>object track</dt>
              <dd className={VALUE_CLASS}>#{concealment.object_track_id}</dd>
            </div>
          </dl>
        </CardContent>
      )}
    </Card>
  )
}
