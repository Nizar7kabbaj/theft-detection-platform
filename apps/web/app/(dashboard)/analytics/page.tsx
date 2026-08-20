import type { Metadata, Route } from "next"
import { cookies } from "next/headers"
import { redirect } from "next/navigation"
import { Suspense } from "react"
import { PageHeader } from "@/components/layout/page-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AbsentPanel } from "@/features/alerts/components/absent-panel"
import { parseBucketUnit } from "@/features/analytics/api/bucket-unit"
import { parseDateRange } from "@/features/analytics/api/date-range"
import {
  decodeSelection,
  RANGE_COOKIE_NAME,
  selectionSearch,
} from "@/features/analytics/api/range-cookie"
import { fetchStats } from "@/features/analytics/api/stats-server"
import { fetchStatsTimeseries } from "@/features/analytics/api/timeseries-server"
import {
  AlertVolumeChartLazy,
  DecisionVolumeChartLazy,
} from "@/features/analytics/components/analytics-charts-lazy"
import { RangeControls } from "@/features/analytics/components/range-controls"
import { StatsCards } from "@/features/analytics/components/stats-cards"
import { TopObjects } from "@/features/analytics/components/top-objects"
import { WindowTotals } from "@/features/analytics/components/window-totals"
import { fetchIdentity } from "@/features/auth/api/identity-server"

export const metadata: Metadata = { title: "analytics" }
export const dynamic = "force-dynamic"

const DESCRIPTION = "alert volume and review throughput over a chosen window"
const OWNED_PARAMS = ["start", "end", "unit"] as const

function windowLabel(start: string, end: string): string {
  const format = (at: Date) =>
    at.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    })
  const lastInstant = new Date(Date.parse(end) - 1)
  return `${format(new Date(start))} to ${format(lastInstant)}, buckets aligned to UTC`
}

async function storedSearch(
  params: Record<string, string | string[] | undefined>,
): Promise<string | null> {
  if (OWNED_PARAMS.some((name) => params[name] !== undefined)) {
    return null
  }
  const store = await cookies()
  const selection = decodeSelection(store.get(RANGE_COOKIE_NAME)?.value)
  if (selection.range.start === null && selection.range.end === null) {
    return null
  }
  return selectionSearch(selection)
}

export default async function AnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const [params, identity] = await Promise.all([searchParams, fetchIdentity()])
  if (!identity.permissions.includes("stats:read")) {
    return (
      <section className="flex flex-1 flex-col gap-5">
        <PageHeader title="analytics" description={DESCRIPTION} />
        <AbsentPanel
          title="analytics is not available to this account"
          reason="reading aggregate counts needs the stats:read permission"
        />
      </section>
    )
  }
  const stored = await storedSearch(params)
  if (stored !== null) {
    redirect(`/analytics?${stored}` as Route)
  }
  const unit = parseBucketUnit(params)
  const range = parseDateRange(params)
  const [stats, series] = await Promise.all([fetchStats(), fetchStatsTimeseries(unit, range)])
  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="analytics" description={DESCRIPTION} />
      <StatsCards stats={stats} />
      <Suspense fallback={null}>
        <RangeControls range={range} unit={unit} />
      </Suspense>
      <p className="text-muted-foreground text-sm">{windowLabel(series.start, series.end)}</p>
      <WindowTotals alerts={series.alerts} decisions={series.decisions} />
      <Card>
        <CardHeader>
          <CardTitle>alerts raised</CardTitle>
          <CardDescription>stacked by severity, {series.alerts.length} buckets</CardDescription>
        </CardHeader>
        <CardContent>
          <AlertVolumeChartLazy buckets={series.alerts} unit={series.unit} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>decisions recorded</CardTitle>
          <CardDescription>stacked by outcome, {series.decisions.length} buckets</CardDescription>
        </CardHeader>
        <CardContent>
          <DecisionVolumeChartLazy buckets={series.decisions} unit={series.unit} />
        </CardContent>
      </Card>
      <TopObjects objects={stats.top_objects} />
      <AbsentPanel
        title="alerts per camera"
        reason="the stats aggregation groups by time and severity only, there is no group-by-camera pipeline"
      />
      <AbsentPanel
        title="detection rate"
        reason="the detections collection has no rows and there is no detections timeseries endpoint"
      />
    </section>
  )
}
