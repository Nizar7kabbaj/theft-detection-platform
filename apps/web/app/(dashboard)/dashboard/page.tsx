import { dehydrate, HydrationBoundary, QueryClient } from "@tanstack/react-query"
import { Suspense } from "react"
import { ConnectionBanner } from "@/components/layout/connection-banner"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertStream } from "@/features/alerts/components/alert-stream"
import { statsQueryKey } from "@/features/analytics/api/stats-key"
import { fetchStats } from "@/features/analytics/api/stats-server"
import { DetectionChart } from "@/features/analytics/components/detection-chart"
import { StatsSummary } from "@/features/analytics/components/stats-summary"

async function StatsPanel() {
  const queryClient = new QueryClient()
  try {
    await queryClient.fetchQuery({ queryKey: statsQueryKey, queryFn: fetchStats })
  } catch {
    return <p className="text-sm text-muted-foreground">today's numbers are unavailable</p>
  }
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <StatsSummary />
    </HydrationBoundary>
  )
}
export default function DashboardPage() {
  return (
    <main className="mx-auto flex min-h-svh max-w-3xl flex-col gap-6 p-8">
      <ConnectionBanner />
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
          <DetectionChart />
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
    </main>
  )
}
