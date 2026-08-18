import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { Concealment } from "@/features/alerts/schemas/alert"

const ROW_CLASS = "flex items-baseline justify-between gap-4 py-1"
const LABEL_CLASS = "text-muted-foreground text-sm"
const VALUE_CLASS = "text-foreground text-sm tabular-nums"

export function EvidencePanel({ concealment }: { concealment: Concealment | null | undefined }) {
  if (concealment === null || concealment === undefined) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>why this fired</CardTitle>
          <CardDescription>no concealment record on this alert</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>why this fired</CardTitle>
        <CardDescription>
          the object left view while a wrist was close enough to have taken it
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl>
          <div className={ROW_CLASS}>
            <dt className={LABEL_CLASS}>object</dt>
            <dd className={VALUE_CLASS}>{concealment.object_class}</dd>
          </div>
          <div className={ROW_CLASS}>
            <dt className={LABEL_CLASS}>last seen at frame</dt>
            <dd className={VALUE_CLASS}>{concealment.last_seen_frame}</dd>
          </div>
          <div className={ROW_CLASS}>
            <dt className={LABEL_CLASS}>frames missing since</dt>
            <dd className={VALUE_CLASS}>{concealment.missing_frames}</dd>
          </div>
          <div className={ROW_CLASS}>
            <dt className={LABEL_CLASS}>grab distance, torso lengths</dt>
            <dd className={VALUE_CLASS}>{concealment.grab_distance.toFixed(3)}</dd>
          </div>
          <div className={ROW_CLASS}>
            <dt className={LABEL_CLASS}>wrist at grab</dt>
            <dd className={VALUE_CLASS}>
              {Math.round(concealment.wrist_x)}, {Math.round(concealment.wrist_y)}
            </dd>
          </div>
          <div className={ROW_CLASS}>
            <dt className={LABEL_CLASS}>person track</dt>
            <dd className={VALUE_CLASS}>{concealment.person_track_id}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  )
}
