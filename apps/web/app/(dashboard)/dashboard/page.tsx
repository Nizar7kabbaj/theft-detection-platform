import { dehydrate, HydrationBoundary, QueryClient } from "@tanstack/react-query"
import type { Metadata } from "next"
import { Suspense } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertStream } from "@/features/alerts/components/alert-stream"
import { todayUtc } from "@/features/analytics/api/date-range"
import { statsQueryKey } from "@/features/analytics/api/stats-key"
import { fetchStats } from "@/features/analytics/api/stats-server"
import { fetchStatsTimeseries } from "@/features/analytics/api/timeseries-server"
import { AlertVolumeChartLazy } from "@/features/analytics/components/analytics-charts-lazy"
import { StatsSummary } from "@/features/analytics/components/stats-summary"

export const metadata: Metadata = { title: "Dashboard" }
export const dynamic = "force-dynamic"

const SKELETON_CLASS = "h-64 w-full animate-pulse rounded-lg bg-muted"

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

async function HourlyAlertPanel() {
  const today = todayUtc()
  try {
    const series = await fetchStatsTimeseries("hour", { start: today, end: today })
    return <AlertVolumeChartLazy buckets={series.alerts} unit={series.unit} />
  } catch {
    return <p className="text-muted-foreground text-sm">hourly volume is unavailable</p>
  }
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
          <CardTitle>alerts today by hour</CardTitle>
          <CardDescription>buckets are UTC, so a day edge sits at 01:00 local</CardDescription>
        </CardHeader>
        <CardContent>
          <Suspense fallback={<div className={SKELETON_CLASS} />}>
            <HourlyAlertPanel />
          </Suspense>
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
