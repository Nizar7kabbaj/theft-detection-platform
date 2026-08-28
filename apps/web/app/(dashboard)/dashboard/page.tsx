import { dehydrate, HydrationBoundary, QueryClient } from "@tanstack/react-query"
import type { Metadata } from "next"
import { Suspense } from "react"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { parseAlertFilters } from "@/features/alerts/api/alert-keys"
import { AlertStream } from "@/features/alerts/components/alert-stream"
import { todayUtc } from "@/features/analytics/api/date-range"
import { statsQueryKey } from "@/features/analytics/api/stats-key"
import { fetchStats } from "@/features/analytics/api/stats-server"
import { fetchStatsTimeseries } from "@/features/analytics/api/timeseries-server"
import { AlertVolumeChartLazy } from "@/features/analytics/components/analytics-charts-lazy"
import { StatsSummary } from "@/features/analytics/components/stats-summary"
import { CameraStatusList } from "@/features/dashboard/components/camera-status-list"
import { CommandStrip } from "@/features/dashboard/components/command-strip"
import { NeedsAttention } from "@/features/dashboard/components/needs-attention"
import { RecentAlerts } from "@/features/dashboard/components/recent-alerts"
import { SeverityFilter } from "@/features/dashboard/components/severity-filter"
import { FloorConsoleLazy } from "@/features/floorplan/components/floor-console-lazy"

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

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const filters = parseAlertFilters(await searchParams)
  return (
    <div className="flex flex-col gap-5">
      <CommandStrip />
      <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>floor</CardTitle>
            <CardDescription>camera positions across the store</CardDescription>
          </CardHeader>
          <CardContent>
            <FloorConsoleLazy />
          </CardContent>
        </Card>
        <div className="flex min-w-0 flex-col gap-5">
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
              <CardTitle>camera status</CardTitle>
              <CardDescription>worst state first</CardDescription>
            </CardHeader>
            <CardContent>
              <Suspense fallback={<div className="h-32 w-full animate-pulse rounded bg-muted" />}>
                <CameraStatusList />
              </Suspense>
            </CardContent>
          </Card>
        </div>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>alert stream</CardTitle>
          <CardDescription>most recent events across every camera</CardDescription>
          <CardAction>
            <SeverityFilter severity={filters.severity} />
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Suspense
            fallback={<div className="h-40 w-full animate-pulse rounded bg-muted" />}
            key={filters.severity ?? "all"}
          >
            <RecentAlerts severity={filters.severity} />
          </Suspense>
          <div className="border-border border-t pt-3">
            <AlertStream />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>needs attention</CardTitle>
          <CardDescription>actionable issues across the store edge</CardDescription>
        </CardHeader>
        <CardContent>
          <Suspense fallback={<div className="h-20 w-full animate-pulse rounded bg-muted" />}>
            <NeedsAttention />
          </Suspense>
        </CardContent>
      </Card>
    </div>
  )
}
