"use client"

import type { Route } from "next"
import { useRouter } from "next/navigation"
import { useCallback } from "react"
import { HISTORY_FILTERS_COOKIE_NAME } from "@/features/history/api/history-cookie"
import { writeCookie } from "@/lib/cookies/write"

export function RestoredNotice() {
  const router = useRouter()

  const reset = useCallback(() => {
    writeCookie(HISTORY_FILTERS_COOKIE_NAME, "", 0)
    router.replace("/history?range=30d" as Route)
  }, [router])

  return (
    <p className="flex flex-wrap items-center gap-3 rounded-lg border border-warning/30 bg-warning/[0.06] px-4 py-2.5 text-sm">
      <span className="size-1.5 shrink-0 rounded-full bg-warning" />
      <span className="text-foreground">filters restored from your last session</span>
      <button
        className="ml-auto rounded-sm font-mono text-[10px] text-warning uppercase tracking-wide underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        onClick={reset}
        type="button"
      >
        reset filters
      </button>
    </p>
  )
}
