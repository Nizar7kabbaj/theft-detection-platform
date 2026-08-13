"use client"

import { Button } from "@/components/ui/button"

export default function DashboardError({ reset }: { reset: () => void }) {
  return (
    <main className="mx-auto flex min-h-svh max-w-3xl flex-col items-start gap-4 p-8">
      <p className="text-sm text-muted-foreground">this section did not load</p>
      <Button onClick={reset} variant="outline">
        try again
      </Button>
    </main>
  )
}
