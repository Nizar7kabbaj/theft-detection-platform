"use client"

import { usePathname } from "next/navigation"
import { useEffect } from "react"
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

  useEffect(() => {
    reportClientError(error.digest, pathname)
  }, [error, pathname])

  return (
    <main className="mx-auto flex min-h-svh max-w-3xl flex-col items-start gap-4 p-8">
      <p className="text-sm text-muted-foreground">this section did not load</p>
      <Button onClick={reset} variant="outline">
        try again
      </Button>
    </main>
  )
}
