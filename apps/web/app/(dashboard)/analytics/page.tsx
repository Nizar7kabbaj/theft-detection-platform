import type { Metadata, Route } from "next"
import { cookies } from "next/headers"
import { redirect } from "next/navigation"
import { Suspense } from "react"
import { PageHeader } from "@/components/layout/page-header"
import { Card } from "@/components/ui/card"
import { AbsentPanel } from "@/features/alerts/components/absent-panel"
import { fetchStatsBreakdown } from "@/features/analytics/api/breakdown-server"
import { DEFAULT_UNIT, parseBucketUnit } from "@/features/analytics/api/bucket-unit"
import { bucketCount, parseDateRange } from "@/features/analytics/api/date-range"
import {
  decodeSelection,
  RANGE_COOKIE_NAME,
  selectionSearch,
} from "@/features/analytics/api/range-cookie"
import { fetchStatsTimeseries } from "@/features/analytics/api/timeseries-server"
import {
  AlertVolumeChartLazy,
  ThroughputChartLazy,
} from "@/features/analytics/components/analytics-charts-lazy"
import {
  BehaviourPanel,
  CameraPanel,
  DurationPanel,
} from "@/features/analytics/components/breakdown-panels"
import { MetricTiles } from "@/features/analytics/components/metric-tiles"
import { RangeBar } from "@/features/analytics/components/range-bar"
import { SeverityPanel } from "@/features/analytics/components/severity-panel"
import { fetchIdentity } from "@/features/auth/api/identity-server"
import { fetchCameras } from "@/features/cameras/api/cameras-server"
import { cameraHealth } from "@/features/cameras/schemas/camera"

export const metadata: Metadata = { title: "analytics" }
export const dynamic = "force-dynamic"

const DESCRIPTION =
  "alert volume, review throughput and severity patterns across the selected range"
const OWNED_PARAMS = ["start", "end", "unit"] as const
const EYEBROW = "font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
const FOOT = "font-mono text-[10px] text-muted-foreground uppercase tracking-[0.14em]"
const EMPTY_CHART = "flex h-64 items-center justify-center text-muted-foreground text-xs"

type Fleet = {
  names: ReadonlyMap<string, string>
  offline: ReadonlySet<string>
}

const EMPTY_FLEET: Fleet = { names: new Map(), offline: new Set() }

function windowLabel(start: string, end: string, unit: string, buckets: number): string {
  const format = (at: Date) =>
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "UTC",
      day: "2-digit",
      month: "short",
      year: "numeric",
    }).format(at)
  const last = new Date(Date.parse(end) - 1)
  return `${format(new Date(start))} to ${format(last)} UTC, ${buckets} ${unit} buckets`
}

async function fleet(canRead: boolean): Promise<Fleet> {
  if (!canRead) {
    return EMPTY_FLEET
  }
  try {
    const cameras = await fetchCameras()
    return {
      names: new Map(cameras.map((camera) => [camera.camera_id, camera.name])),
      offline: new Set(
        cameras
          .filter((camera) => cameraHealth(camera).state === "offline")
          .map((camera) => camera.camera_id),
      ),
    }
  } catch {
    return EMPTY_FLEET
  }
}

async function storedSearch(
  params: Record<string, string | string[] | undefined>,
): Promise<string | null> {
  if (OWNED_PARAMS.some((name) => params[name] !== undefined)) {
    return null
  }
  const store = await cookies()
  const stored = store.get(RANGE_COOKIE_NAME)?.value
  if (stored === undefined || stored === "") {
    return null
  }
  const selection = decodeSelection(stored)
  if (
    selection.range.start === null &&
    selection.range.end === null &&
    selection.unit === DEFAULT_UNIT
  ) {
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
      <section className="flex flex-1 flex-col gap-6">
        <PageHeader description={DESCRIPTION} title="analytics" />
        <AbsentPanel
          reason="reading aggregate counts needs the stats:read permission"
          title="analytics is not available to this account"
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
  const [series, breakdown, cameras] = await Promise.all([
    fetchStatsTimeseries(unit, range),
    fetchStatsBreakdown(range),
    fleet(identity.permissions.includes("camera:read")),
  ])

  const asked = bucketCount(range, unit)
  const shortened = asked !== null && asked > series.alerts.length
  const raised = series.alerts.reduce((total, bucket) => total + bucket.total, 0)
  const decided = series.decisions.reduce((total, bucket) => total + bucket.total, 0)

  return (
    <section className="flex flex-1 flex-col gap-6">
      <PageHeader description={DESCRIPTION} title="analytics" />

      <div className="flex flex-col gap-2">
        <Suspense fallback={null}>
          <RangeBar range={range} unit={unit} />
        </Suspense>
        <p className={FOOT}>
          {windowLabel(series.start, series.end, series.unit, series.alerts.length)}
        </p>
        {shortened ? (
          <p className="font-mono text-[10px] text-warning uppercase tracking-[0.14em]">
            window shortened by the server to the most recent buckets
          </p>
        ) : null}
      </div>

      <MetricTiles alerts={series.alerts} breakdown={breakdown} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card className="gap-4 p-5">
          <p className={EYEBROW}>activity timeline</p>
          <h2 className="font-medium text-base text-foreground">alert volume over time</h2>
          <p className="text-[11px] text-muted-foreground leading-[1.45]">
            stacked by severity, click a bar to open that day in history
          </p>
          {raised === 0 ? (
            <p className={EMPTY_CHART}>no alerts were raised in this window</p>
          ) : (
            <AlertVolumeChartLazy buckets={series.alerts} unit={series.unit} />
          )}
        </Card>
        <SeverityPanel buckets={series.alerts} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="gap-4 p-5">
          <p className={EYEBROW}>review throughput</p>
          <h2 className="font-medium text-base text-foreground">raised versus decided</h2>
          <p className="text-[11px] text-muted-foreground leading-[1.45]">
            decisions are counted when they were made, not when the alert was raised
          </p>
          {raised === 0 && decided === 0 ? (
            <p className={EMPTY_CHART}>nothing was raised or decided in this window</p>
          ) : (
            <ThroughputChartLazy
              alerts={series.alerts}
              decisions={series.decisions}
              unit={series.unit}
            />
          )}
        </Card>
        {breakdown === null ? (
          <AbsentPanel
            reason="time to decision needs an aggregation over decided_at, there is no endpoint for it yet"
            title="review duration"
          />
        ) : (
          <DurationPanel duration={breakdown.duration} />
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {breakdown === null ? (
          <AbsentPanel
            reason="grouping alerts by behaviour class inside a window needs an aggregation that does not exist yet"
            title="behaviour ranking"
          />
        ) : (
          <BehaviourPanel types={breakdown.alert_types} />
        )}
        {breakdown === null ? (
          <AbsentPanel
            reason="grouping alerts by camera inside a window needs an aggregation that does not exist yet"
            title="camera workload"
          />
        ) : (
          <CameraPanel
            cameras={breakdown.cameras}
            names={cameras.names}
            offline={cameras.offline}
          />
        )}
      </div>

      <div className="flex items-center justify-between border-border/60 border-t pt-4">
        <p className={FOOT}>source: alert archive</p>
        <p className={FOOT}>{series.unit} buckets, times in UTC</p>
      </div>
    </section>
  )
}
