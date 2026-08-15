import { dehydrate, HydrationBoundary, QueryClient } from "@tanstack/react-query"
import type { Metadata } from "next"
import { Suspense } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertStream } from "@/features/alerts/components/alert-stream"
import { statsQueryKey } from "@/features/analytics/api/stats-key"
import { fetchStats } from "@/features/analytics/api/stats-server"
import { DetectionChartLazy } from "@/features/analytics/components/detection-chart-lazy"
import { StatsSummary } from "@/features/analytics/components/stats-summary"

export const metadata: Metadata = { title: "Dashboard" }

async function StatsPanel() {
  const queryClient = new QueryClient()
  try {
    await queryClient.fetchQuery({ queryKey: statsQueryKey, queryFn: fetchStats })
  } catch {
    return <p className="text-muted-foreground text-sm">today's numbers are unavailable</p>
  }
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <StatsSummary />
    </HydrationBoundary>
  )
}

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader>
          <CardTitle>today</CardTitle>
          <CardDescription>read on the server, hydrated into the client cache</CardDescription>
        </CardHeader>
        <CardContent>
          <Suspense fallback={<div className="h-16 w-full animate-pulse rounded bg-muted" />}>
            <StatsPanel />
          </Suspense>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>detections per hour</CardTitle>
          <CardDescription>static sample, no api calls in this scope</CardDescription>
        </CardHeader>
        <CardContent>
          <DetectionChartLazy />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>alert stream</CardTitle>
          <CardDescription>live connection state and the last event received</CardDescription>
        </CardHeader>
        <CardContent>
          <AlertStream />
        </CardContent>
      </Card>
    </div>
  )
}
