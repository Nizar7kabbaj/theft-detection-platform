"use client"
import { Button } from "@/components/ui/button"
import { useAcknowledgeDetail, useAlertDetail } from "@/features/alerts/hooks/use-alert-detail"
import type { AlertDetail } from "@/features/alerts/schemas/alert"

const CHIP_CLASS =
  "inline-flex items-center rounded-md border border-border px-2 py-0.5 font-mono text-[11px] text-muted-foreground uppercase tracking-[0.12em]"

export function AcknowledgeButton({ alert }: { alert: AlertDetail }) {
  const { data } = useAlertDetail(alert._id, alert)
  const mutation = useAcknowledgeDetail(alert._id)
  const settled = data.decision !== "DECISION_UNSPECIFIED"
  const state = data.acknowledged ? (settled ? "closed" : "seen") : "open"
  return (
    <div className="flex items-center gap-3">
      <span className={CHIP_CLASS}>{state}</span>
      {data.acknowledged ? null : (
        <Button
          disabled={mutation.isPending}
          onClick={() => mutation.mutate()}
          size="sm"
          variant="default"
        >
          {mutation.isPending ? "sending" : "acknowledge"}
        </Button>
      )}
      {mutation.isError ? (
        <span className="text-destructive text-xs">not saved, try again</span>
      ) : null}
    </div>
  )
}
