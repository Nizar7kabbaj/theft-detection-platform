"use client"

import type { Route } from "next"
import { useRouter } from "next/navigation"
import { useCallback, useState } from "react"
import { ALERT_FILTERS_COOKIE_NAME } from "@/features/alerts/api/alert-cookie"
import type { AlertFilters, CameraOption } from "@/features/alerts/api/alert-keys"
import { AlertFilterControls } from "@/features/alerts/components/alert-filters"
import { AlertTable } from "@/features/alerts/components/alert-table"
import { QueueSummary } from "@/features/alerts/components/queue-summary"
import type { Stats } from "@/features/analytics/schemas/stats"
import { writeCookie } from "@/lib/cookies/write"

export function AlertsWorkspace({
  filters,
  cameras,
  canAcknowledge,
  stats,
  restored,
}: {
  filters: AlertFilters
  cameras: CameraOption[]
  canAcknowledge: boolean
  stats: Stats | null
  restored: boolean
}) {
  const router = useRouter()
  const [text, setText] = useState("")

  const reset = useCallback(() => {
    setText("")
    writeCookie(ALERT_FILTERS_COOKIE_NAME, "", 0)
    router.replace("/alerts" as Route)
  }, [router])

  return (
    <div className="flex flex-col gap-5">
      <QueueSummary filters={filters} stats={stats} />
      {restored ? (
        <p className="flex flex-wrap items-center gap-3 rounded-lg border border-warning/30 bg-warning/[0.06] px-4 py-2.5 text-sm">
          <span className="size-1.5 shrink-0 rounded-full bg-warning" />
          <span className="text-foreground">filters restored from your last session</span>
          <button
            className="ml-auto rounded-sm font-mono text-[10px] text-warning uppercase tracking-wide underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
            onClick={reset}
            type="button"
          >
            show all events
          </button>
        </p>
      ) : null}
      <AlertFilterControls
        cameras={cameras}
        filters={filters}
        onReset={reset}
        onTextChange={setText}
        text={text}
      />
      <AlertTable canAcknowledge={canAcknowledge} filters={filters} text={text} />
    </div>
  )
}
