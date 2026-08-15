"use client"
import { RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"

export function NewAlertPill({ count, onRefresh }: { count: number; onRefresh: () => void }) {
  if (count === 0) {
    return null
  }

  return (
    <div
      aria-live="polite"
      className="flex items-center gap-3 rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm"
    >
      <span className="text-muted-foreground">
        {count === 1 ? "1 alert changed" : `${count} alerts changed`}
      </span>
      <Button onClick={onRefresh} size="xs" variant="outline">
        <RefreshCw aria-hidden="true" />
        refresh
      </Button>
    </div>
  )
}
