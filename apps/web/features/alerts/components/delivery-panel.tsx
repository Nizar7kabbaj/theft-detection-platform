import type { z } from "zod/mini"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { deliveryRecordSchema, deliveryStatusSchema } from "@/features/alerts/schemas/alert"

type DeliveryStatusView = z.output<typeof deliveryStatusSchema>
type DeliveryRecord = z.output<typeof deliveryRecordSchema>

const LABEL_CLASS = "font-mono text-[10px] text-muted-foreground uppercase tracking-[0.16em]"
const NOTE_CLASS = "font-mono text-muted-foreground text-xs"

const STATE_TEXT: Record<string, string> = {
  sent: "text-success",
  buffered: "text-warning",
  pending: "text-muted-foreground",
  sending: "text-muted-foreground",
  failed: "text-destructive",
  dead: "text-destructive",
  unknown: "text-muted-foreground",
}

function formatStamp(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function DeliveryRow({ record }: { record: DeliveryRecord }) {
  const tone = STATE_TEXT[record.state] ?? "text-muted-foreground"
  return (
    <div className="flex flex-col gap-1 border-border border-t pt-2 first:border-t-0 first:pt-0">
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-mono text-foreground text-sm">
          {record.channel} · {record.recipient}
        </p>
        <p className={`font-mono text-sm ${tone}`}>{record.state}</p>
      </div>
      <p className={NOTE_CLASS}>
        {record.attempts} attempt{record.attempts === 1 ? "" : "s"}
        {record.requeue_count > 0 ? ` · ${record.requeue_count} requeued` : ""}
        {record.last_error_class ? ` · ${record.last_error_class}` : ""}
      </p>
      <p className={NOTE_CLASS}>last change {formatStamp(record.updated_at)}</p>
    </div>
  )
}

export function DeliveryPanel({
  delivery,
  dispatchFailed,
}: {
  delivery: DeliveryStatusView | null | undefined
  dispatchFailed: boolean
}) {
  const unreachable = delivery === null || delivery === undefined
  const unseen = !unreachable && !delivery.known
  return (
    <Card>
      <CardHeader>
        <p className={LABEL_CLASS}>notification</p>
        <CardTitle className="text-lg">delivery</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {unreachable ? (
          <p className={NOTE_CLASS}>delivery service did not answer, state unknown</p>
        ) : null}
        {unseen && dispatchFailed ? (
          <p className={NOTE_CLASS}>
            handoff to the delivery service failed, this alert was never queued
          </p>
        ) : null}
        {unseen && !dispatchFailed ? (
          <p className={NOTE_CLASS}>this alert never reached the delivery service</p>
        ) : null}
        {!unreachable && delivery.known
          ? delivery.records.map((record) => (
              <DeliveryRow key={`${record.channel}-${record.recipient}`} record={record} />
            ))
          : null}
      </CardContent>
    </Card>
  )
}
