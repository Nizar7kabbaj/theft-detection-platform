"use client"

import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { alertKeys } from "@/features/alerts/api/alert-keys"
import { decideAlert } from "@/features/alerts/api/alerts-client"
import { DECISION_LABEL } from "@/features/alerts/lib/format"
import type { AlertDetail, Decision } from "@/features/alerts/schemas/alert"

const CHOICES: readonly Decision[] = ["DECISION_CONFIRMED", "DECISION_DISMISSED", "DECISION_UNSURE"]

export function DecisionControls({ alert }: { alert: AlertDetail }) {
  const queryClient = useQueryClient()
  const [current, setCurrent] = useState<AlertDetail>(alert)
  const [pendingChoice, setPendingChoice] = useState<Decision | null>(null)
  const [failed, setFailed] = useState(false)

  const mutation = useMutation({
    mutationFn: (decision: Decision) => decideAlert(current._id, decision),
    onSuccess: (updated) => {
      setCurrent(updated)
      setFailed(false)
      void queryClient.invalidateQueries({ queryKey: alertKeys.all })
    },
    onError: () => setFailed(true),
    onSettled: () => setPendingChoice(null),
  })

  const decided = current.decision !== "DECISION_UNSPECIFIED"

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
      <div className="flex flex-col gap-1">
        <h2 className="font-medium text-foreground text-sm">operator decision</h2>
        <p className="text-muted-foreground text-xs">
          {decided
            ? `recorded as ${DECISION_LABEL[current.decision]}`
            : "this judgement becomes a labelled training case"}
        </p>
      </div>
      {pendingChoice === null ? (
        <div className="flex flex-wrap gap-2">
          {CHOICES.map((choice) => (
            <Button
              disabled={mutation.isPending}
              key={choice}
              onClick={() => setPendingChoice(choice)}
              size="sm"
              variant={current.decision === choice ? "default" : "outline"}
            >
              {DECISION_LABEL[choice]}
            </Button>
          ))}
          {decided ? (
            <Button
              disabled={mutation.isPending}
              onClick={() => mutation.mutate("DECISION_UNSPECIFIED")}
              size="sm"
              variant="ghost"
            >
              clear
            </Button>
          ) : null}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-foreground text-sm">
            record this alert as {DECISION_LABEL[pendingChoice]}?
          </p>
          <Button
            disabled={mutation.isPending}
            onClick={() => mutation.mutate(pendingChoice)}
            size="sm"
            variant="default"
          >
            {mutation.isPending ? "sending" : "yes"}
          </Button>
          <Button
            disabled={mutation.isPending}
            onClick={() => setPendingChoice(null)}
            size="sm"
            variant="outline"
          >
            cancel
          </Button>
        </div>
      )}
      {failed ? (
        <p className="text-destructive text-xs">the decision was not saved. try again</p>
      ) : null}
    </div>
  )
}
