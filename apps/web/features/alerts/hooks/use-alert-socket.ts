"use client"
import { type InfiniteData, useQueryClient } from "@tanstack/react-query"
import { useCallback, useRef, useState } from "react"
import { type AlertFilters, alertKeys } from "@/features/alerts/api/alert-keys"
import { type AlertPage, alertResponseSchema } from "@/features/alerts/schemas/alert"
import type { StreamEnvelope } from "@/lib/websocket/envelope"
import { useStream } from "@/lib/websocket/use-stream"

type AlertSocketState = {
  pendingCount: number
  clearPending: () => void
}

export function useAlertSocket(filters: AlertFilters): AlertSocketState {
  const queryClient = useQueryClient()
  const [pendingCount, setPendingCount] = useState(0)
  const filtersRef = useRef(filters)
  filtersRef.current = filters

  const onEvent = useCallback(
    (envelope: StreamEnvelope) => {
      if (envelope.event === "created" || envelope.event === "deleted") {
        setPendingCount((count) => count + 1)
        return
      }
      if (envelope.event !== "acknowledged") {
        return
      }
      const parsed = alertResponseSchema.safeParse(envelope.data)
      if (!parsed.success) {
        return
      }
      const alert = parsed.data
      const key = alertKeys.list(filtersRef.current)
      let seen = false
      queryClient.setQueryData<InfiniteData<AlertPage, string | null>>(key, (current) => {
        if (current === undefined) {
          return current
        }
        const pages = current.pages.map((page) => {
          if (!page.items.some((item) => item._id === alert._id)) {
            return page
          }
          seen = true
          return {
            ...page,
            items: page.items.map((item) => (item._id === alert._id ? alert : item)),
          }
        })
        return seen ? { ...current, pages } : current
      })
      if (!seen) {
        setPendingCount((count) => count + 1)
      }
    },
    [queryClient],
  )

  useStream("alerts", onEvent)

  const clearPending = useCallback(() => {
    setPendingCount(0)
  }, [])

  return { pendingCount, clearPending }
}
