"use client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useAlertDetail } from "@/features/alerts/hooks/use-alert-detail"
import { DECISION_LABEL, formatTimestamp } from "@/features/alerts/lib/format"
import type { AlertDetail } from "@/features/alerts/schemas/alert"

const LABEL_CLASS = "font-mono text-[10px] text-muted-foreground uppercase tracking-[0.16em]"
const TIME_CLASS = "font-mono text-foreground text-xs tabular-nums"
const WHO_CLASS = "font-mono text-muted-foreground text-xs"

type Entry = { at: string; label: string; who: string | null }

function buildEntries(alert: AlertDetail): Entry[] {
  const entries: Entry[] = [
    { at: alert.occurred_at, label: "occurred", who: null },
    { at: alert.created_at, label: "created", who: null },
  ]
  if (alert.acknowledged_at !== null && alert.acknowledged_at !== undefined) {
    entries.push({ at: alert.acknowledged_at, label: "acknowledged", who: null })
  }
  if (alert.decided_at !== null && alert.decided_at !== undefined) {
    entries.push({
      at: alert.decided_at,
      label: DECISION_LABEL[alert.decision],
      who: alert.decided_by ?? null,
    })
  }
  return entries.sort((a, b) => Date.parse(a.at) - Date.parse(b.at))
}

export function AuditTrail({ alert }: { alert: AlertDetail }) {
  const { data } = useAlertDetail(alert._id, alert)
  const entries = buildEntries(data)
  return (
    <Card>
      <CardHeader>
        <p className={LABEL_CLASS}>audit trail</p>
        <CardTitle className="text-lg">recorded timestamps</CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="flex flex-col gap-3">
          {entries.map((entry) => (
            <li className="flex flex-col gap-0.5" key={`${entry.label}-${entry.at}`}>
              <span className={LABEL_CLASS}>{entry.label}</span>
              <span className={TIME_CLASS}>{formatTimestamp(entry.at)} utc</span>
              {entry.who === null ? null : <span className={WHO_CLASS}>by {entry.who}</span>}
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  )
}
