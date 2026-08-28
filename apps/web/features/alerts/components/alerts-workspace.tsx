"use client"

import type { Route } from "next"
import { useRouter } from "next/navigation"
import { useCallback, useState } from "react"
import { Button } from "@/components/ui/button"
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
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-2.5">
          <span className="font-mono text-[11px] text-warning uppercase tracking-wider">
            filters restored from your last session
          </span>
          <Button onClick={reset} size="xs" variant="outline">
            show all events
          </Button>
        </div>
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
