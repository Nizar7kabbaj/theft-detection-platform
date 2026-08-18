"use client"

import { type InfiniteData, useMutation, useQueryClient } from "@tanstack/react-query"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { type AlertFilters, alertKeys } from "@/features/alerts/api/alert-keys"
import { acknowledgeAlert } from "@/features/alerts/api/alerts-client"
import type { Route } from "next"
import type { Alert, AlertPage } from "@/features/alerts/schemas/alert"

const CELL_CLASS = "px-3 py-2 align-middle"

const SEVERITY_CLASS: Record<Alert["severity"], string> = {
  SEVERITY_UNSPECIFIED: "text-muted-foreground",
  SEVERITY_INFO: "text-muted-foreground",
  SEVERITY_NOTICE: "text-chart-2",
  SEVERITY_WARNING: "text-warning",
  SEVERITY_CRITICAL: "text-destructive",
}

const SEVERITY_LABEL: Record<Alert["severity"], string> = {
  SEVERITY_UNSPECIFIED: "unspecified",
  SEVERITY_INFO: "info",
  SEVERITY_NOTICE: "notice",
  SEVERITY_WARNING: "warning",
  SEVERITY_CRITICAL: "critical",
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString("en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "UTC",
  })
}

export function AlertRow({
  alert,
  filters,
  canAcknowledge,
}: {
  alert: Alert
  filters: AlertFilters
  canAcknowledge: boolean
}) {
  const queryClient = useQueryClient()
  const router = useRouter()
  const key = alertKeys.list(filters)
  const href = `/alerts/${alert._id}` as Route

  const mutation = useMutation({
    mutationFn: () => acknowledgeAlert(alert._id),
    onSuccess: (updated) => {
      queryClient.setQueryData<InfiniteData<AlertPage, string | null>>(key, (current) => {
        if (current === undefined) {
          return current
        }
        return {
          ...current,
          pages: current.pages.map((page) => ({
            ...page,
            items: page.items.map((item) => (item._id === updated._id ? updated : item)),
          })),
        }
      })
    },
  })

  const openDetail = () => {
    const selection = window.getSelection()
    if (selection !== null && selection.toString().length > 0) {
      return
    }
    router.push(href)
  }

  return (
    <tr
      className="cursor-pointer border-border border-b last:border-b-0 hover:bg-muted/40"
      onClick={openDetail}
    >
      <td className={`${CELL_CLASS} whitespace-nowrap tabular-nums text-muted-foreground`}>
        <Link
          className="underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          href={href}
          onClick={(event) => event.stopPropagation()}
        >
          {formatTime(alert.created_at)}
        </Link>
      </td>
      <td className={CELL_CLASS}>{alert.camera_id}</td>
      <td className={`${CELL_CLASS} ${SEVERITY_CLASS[alert.severity]}`}>
        {SEVERITY_LABEL[alert.severity]}
      </td>
      <td className={CELL_CLASS}>{alert.object_name}</td>
      <td className={`${CELL_CLASS} tabular-nums`}>
        {alert.confidence === null || alert.confidence === undefined
          ? "—"
          : alert.confidence.toFixed(2)}
      </td>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: the time cell carries a real link for keyboard users */}
      <td className={CELL_CLASS} onClick={(event) => event.stopPropagation()}>
        {alert.acknowledged ? (
          <span className="text-muted-foreground">acknowledged</span>
        ) : canAcknowledge ? (
          <Button
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
            size="xs"
            variant="outline"
          >
            {mutation.isPending ? "sending" : "acknowledge"}
          </Button>
        ) : (
          <span className="text-muted-foreground">open</span>
        )}
      </td>
    </tr>
  )
}
