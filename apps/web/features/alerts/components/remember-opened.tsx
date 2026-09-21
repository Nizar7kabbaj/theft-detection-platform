"use client"
import { useEffect } from "react"
import { rememberOpened } from "@/features/alerts/lib/last-opened"

export function RememberOpened({ alertId }: { alertId: string }) {
  useEffect(() => {
    rememberOpened(alertId)
  }, [alertId])
  return null
}
