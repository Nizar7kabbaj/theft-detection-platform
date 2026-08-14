"use client"
import { useQueryErrorResetBoundary } from "@tanstack/react-query"
import { usePathname } from "next/navigation"
import { useCallback, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { reportClientError } from "@/lib/monitoring/report-client-error"
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const pathname = usePathname()
  const { reset: resetQueries } = useQueryErrorResetBoundary()
  useEffect(() => {
    reportClientError(error.digest, pathname)
  }, [error, pathname])
  const onRetry = useCallback(() => {
    resetQueries()
    reset()
  }, [resetQueries, reset])
  return (
    <main className="mx-auto flex min-h-svh max-w-3xl flex-col items-start gap-4 p-8">
      <p className="text-sm text-muted-foreground">this section did not load</p>
      {error.digest === undefined ? null : (
        <p className="text-xs text-muted-foreground tabular-nums">reference {error.digest}</p>
      )}
      <Button onClick={onRetry} variant="outline">
        try again
      </Button>
    </main>
  )
}
