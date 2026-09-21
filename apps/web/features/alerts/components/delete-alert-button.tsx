"use client"
import type { Route } from "next"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useDeleteAlert } from "@/features/alerts/hooks/use-alert-detail"

export function DeleteAlertButton({ alertId }: { alertId: string }) {
  const router = useRouter()
  const mutation = useDeleteAlert(alertId)
  const [confirming, setConfirming] = useState(false)
  if (!confirming) {
    return (
      <Button onClick={() => setConfirming(true)} size="sm" variant="ghost">
        delete
      </Button>
    )
  }
  return (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground text-xs">delete permanently? this cannot be undone</span>
      <Button
        disabled={mutation.isPending}
        onClick={() =>
          mutation.mutate(undefined, { onSuccess: () => router.replace("/alerts" as Route) })
        }
        size="sm"
        variant="destructive"
      >
        {mutation.isPending ? "deleting" : "confirm delete"}
      </Button>
      <Button
        disabled={mutation.isPending}
        onClick={() => setConfirming(false)}
        size="sm"
        variant="ghost"
      >
        cancel
      </Button>
      {mutation.isError ? (
        <span className="text-destructive text-xs">not deleted, try again</span>
      ) : null}
    </div>
  )
}
