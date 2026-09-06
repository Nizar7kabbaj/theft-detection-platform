"use client"
import type { Route } from "next"
import { useRouter } from "next/navigation"
import { useCallback } from "react"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"
import {
  type ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import type {
  AlertBucket,
  BucketUnit,
  DecisionBucket,
} from "@/features/analytics/schemas/timeseries"
import { STORE_TIME_LABEL, STORE_TIME_ZONE } from "@/lib/time/zone"

const ALERT_CONFIG = {
  info: { label: "info", color: "var(--chart-3)" },
  notice: { label: "notice", color: "var(--chart-2)" },
  warning: { label: "warning", color: "var(--chart-1)" },
  critical: { label: "critical", color: "var(--chart-4)" },
  unspecified: { label: "unspecified", color: "var(--chart-5)" },
} satisfies ChartConfig

const THROUGHPUT_CONFIG = {
  raised: { label: "raised", color: "var(--chart-2)" },
  decided: { label: "decided", color: "var(--chart-3)" },
} satisfies ChartConfig

const ALERT_KEYS = ["unspecified", "info", "notice", "warning", "critical"] as const
const CHART_CLASS =
  "aspect-auto h-64 w-full [&_.recharts-cartesian-grid_line]:stroke-border/50 motion-reduce:[&_.recharts-layer]:animate-none"
const AXIS_PROPS = {
  axisLine: false,
  tickLine: false,
  tickMargin: 8,
  tick: { fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--muted-foreground)" },
} as const

function tickLabel(bucket: string, unit: BucketUnit): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: STORE_TIME_ZONE,
    ...(unit === "hour"
      ? { hour: "2-digit", minute: "2-digit", hour12: false }
      : { day: "2-digit", month: "short" }),
  }).format(new Date(bucket))
}

function fullLabel(bucket: string, unit: BucketUnit): string {
  const stamp = new Intl.DateTimeFormat("en-GB", {
    timeZone: STORE_TIME_ZONE,
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(unit === "hour" ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
  }).format(new Date(bucket))
  return `${stamp} ${STORE_TIME_LABEL}`
}

function useBucketLink(): (bucket: string) => void {
  const router = useRouter()
  return useCallback(
    (bucket: string) => {
      const day = bucket.slice(0, 10)
      const search = new URLSearchParams({ start: day, end: day })
      router.push(`/history?${search.toString()}` as Route)
    },
    [router],
  )
}

export function AlertVolumeChart({
  buckets,
  unit,
}: {
  buckets: readonly AlertBucket[]
  unit: BucketUnit
}) {
  const open = useBucketLink()
  const data = buckets.map((entry) => ({ ...entry, label: tickLabel(entry.bucket, unit) }))
  return (
    <ChartContainer className={CHART_CLASS} config={ALERT_CONFIG}>
      <BarChart accessibilityLayer data={data} margin={{ left: 4, right: 4, top: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis {...AXIS_PROPS} dataKey="label" interval="preserveStartEnd" minTickGap={16} />
        <YAxis {...AXIS_PROPS} allowDecimals={false} width={28} />
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={(_value, payload) => {
                const first = payload?.[0]?.payload as { bucket?: string } | undefined
                return first?.bucket === undefined ? "" : fullLabel(first.bucket, unit)
              }}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        {ALERT_KEYS.map((key, index) => (
          <Bar
            className="cursor-pointer"
            dataKey={key}
            fill={`var(--color-${key})`}
            key={key}
            onClick={(data) => {
              const row = data as unknown as { payload?: { bucket?: string } }
              const bucket = row.payload?.bucket
              if (bucket !== undefined) {
                open(bucket)
              }
            }}
            radius={index === ALERT_KEYS.length - 1 ? [3, 3, 0, 0] : 0}
            stackId="alerts"
          />
        ))}
      </BarChart>
    </ChartContainer>
  )
}

export function ThroughputChart({
  alerts,
  decisions,
  unit,
}: {
  alerts: readonly AlertBucket[]
  decisions: readonly DecisionBucket[]
  unit: BucketUnit
}) {
  const decided = new Map(decisions.map((entry) => [entry.bucket, entry.total]))
  const data = alerts.map((entry) => ({
    bucket: entry.bucket,
    label: tickLabel(entry.bucket, unit),
    raised: entry.total,
    decided: decided.get(entry.bucket) ?? 0,
  }))
  return (
    <ChartContainer className={CHART_CLASS} config={THROUGHPUT_CONFIG}>
      <BarChart accessibilityLayer data={data} margin={{ left: 4, right: 4, top: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis {...AXIS_PROPS} dataKey="label" interval="preserveStartEnd" minTickGap={16} />
        <YAxis {...AXIS_PROPS} allowDecimals={false} width={28} />
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={(_value, payload) => {
                const first = payload?.[0]?.payload as { bucket?: string } | undefined
                return first?.bucket === undefined ? "" : fullLabel(first.bucket, unit)
              }}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        <Bar dataKey="raised" fill="var(--color-raised)" radius={[3, 3, 0, 0]} />
        <Bar dataKey="decided" fill="var(--color-decided)" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ChartContainer>
  )
}
