"use client"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Check, CircleHelp, X } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { alertKeys } from "@/features/alerts/api/alert-keys"
import { decideAlert } from "@/features/alerts/api/alerts-client"
import { useAlertDetail } from "@/features/alerts/hooks/use-alert-detail"
import { DECISION_LABEL } from "@/features/alerts/lib/format"
import type { AlertDetail, Decision } from "@/features/alerts/schemas/alert"

const CHOICES: readonly { icon: typeof Check; value: Decision }[] = [
  { icon: Check, value: "DECISION_CONFIRMED" },
  { icon: X, value: "DECISION_DISMISSED" },
  { icon: CircleHelp, value: "DECISION_UNSURE" },
]
const ICONS: Record<Decision, typeof Check> = {
  DECISION_UNSPECIFIED: CircleHelp,
  DECISION_CONFIRMED: Check,
  DECISION_DISMISSED: X,
  DECISION_UNSURE: CircleHelp,
}
const PILL_CLASS: Record<Decision, string> = {
  DECISION_UNSPECIFIED: "bg-muted text-muted-foreground",
  DECISION_CONFIRMED: "bg-destructive text-destructive-foreground",
  DECISION_DISMISSED: "bg-success text-success-foreground",
  DECISION_UNSURE: "bg-warning text-warning-foreground",
}
const LABEL_CLASS = "font-mono text-[10px] text-muted-foreground uppercase tracking-[0.16em]"
const PILL_BASE =
  "group inline-flex h-12 items-center gap-2 rounded-full pr-2 pl-3.5 font-medium text-base shadow-panel [&_svg]:size-5"
const REVEAL_CLASS =
  "flex max-w-0 items-center gap-1.5 overflow-hidden whitespace-nowrap opacity-0 transition-[max-width,opacity] duration-200 ease-out group-hover:max-w-40 group-hover:opacity-100 group-focus-within:max-w-40 group-focus-within:opacity-100"
const CLEAR_CLASS =
  "flex size-8 shrink-0 items-center justify-center rounded-full bg-black/20 transition-colors hover:bg-black/35"

export function DecisionControls({ alert }: { alert: AlertDetail }) {
  const queryClient = useQueryClient()
  const { data } = useAlertDetail(alert._id, alert)
  const [pending, setPending] = useState<Decision | null>(null)
  const mutation = useMutation({
    mutationFn: (decision: Decision) => decideAlert(data._id, decision),
    onSuccess: (updated) => {
      queryClient.setQueryData<AlertDetail>(alertKeys.detail(data._id), updated)
      void queryClient.invalidateQueries({ queryKey: alertKeys.all })
    },
    onSettled: () => setPending(null),
  })

  if (data.decision !== "DECISION_UNSPECIFIED") {
    const Icon = ICONS[data.decision]
    return (
      <div className="sticky bottom-0 z-10 flex justify-end py-2">
        <span className={`${PILL_BASE} ${PILL_CLASS[data.decision]}`}>
          <Icon className="ml-0.5 shrink-0" />
          <span className={REVEAL_CLASS}>
            {DECISION_LABEL[data.decision]}
            <button
              aria-label="clear this decision"
              className={CLEAR_CLASS}
              disabled={mutation.isPending}
              onClick={() => mutation.mutate("DECISION_UNSPECIFIED")}
              type="button"
            >
              <X className="size-3.5" />
            </button>
          </span>
        </span>
      </div>
    )
  }

  return (
    <div className="sticky bottom-0 z-10 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-border bg-card/95 p-4 shadow-panel backdrop-blur">
      <div className="flex flex-col gap-1">
        <p className={LABEL_CLASS}>operator decision</p>
        <h2 className="font-semibold text-foreground text-lg tracking-tight">
          {pending === null ? "is this a theft?" : `record as ${DECISION_LABEL[pending]}?`}
        </h2>
        <p className="text-muted-foreground text-xs">
          this judgement becomes a labelled training case
        </p>
      </div>
      {pending === null ? (
        <div className="flex flex-wrap items-center gap-2">
          {CHOICES.map(({ icon: Icon, value }) => (
            <Button
              disabled={mutation.isPending}
              key={value}
              onClick={() => setPending(value)}
              variant="outline"
            >
              <Icon />
              {DECISION_LABEL[value]}
            </Button>
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Button
            disabled={mutation.isPending}
            onClick={() => mutation.mutate(pending)}
            variant="default"
          >
            {mutation.isPending ? "sending" : "yes, record it"}
          </Button>
          <Button disabled={mutation.isPending} onClick={() => setPending(null)} variant="outline">
            cancel
          </Button>
        </div>
      )}
      {mutation.isError ? (
        <p className="w-full text-destructive text-xs">the decision was not saved. try again</p>
      ) : null}
    </div>
  )
}
