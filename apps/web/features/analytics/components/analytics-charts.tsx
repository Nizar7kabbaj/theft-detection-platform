"use client"
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

const ALERT_CONFIG = {
  critical: { label: "critical", color: "var(--chart-4)" },
  warning: { label: "warning", color: "var(--chart-1)" },
  notice: { label: "notice", color: "var(--chart-2)" },
  info: { label: "info", color: "var(--chart-3)" },
  unspecified: { label: "unspecified", color: "var(--chart-5)" },
} satisfies ChartConfig

const DECISION_CONFIG = {
  confirmed: { label: "confirmed", color: "var(--chart-4)" },
  dismissed: { label: "dismissed", color: "var(--chart-3)" },
  unsure: { label: "unsure", color: "var(--chart-1)" },
} satisfies ChartConfig

const ALERT_KEYS = ["unspecified", "info", "notice", "warning", "critical"] as const
const DECISION_KEYS = ["dismissed", "unsure", "confirmed"] as const

const CHART_CLASS = "aspect-auto h-56 w-full [&_.recharts-cartesian-grid_line]:stroke-border/50"
const AXIS_PROPS = {
  axisLine: false,
  tickLine: false,
  tickMargin: 8,
  tick: { fontSize: 9, fontFamily: "var(--font-mono)", fill: "var(--muted-foreground)" },
} as const

function tickLabel(bucket: string, unit: BucketUnit): string {
  const at = new Date(bucket)
  if (unit === "hour") {
    return at.toLocaleString("en-GB", { day: "2-digit", hour: "2-digit", timeZone: "UTC" })
  }
  return at.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" })
}

function fullLabel(bucket: string, unit: BucketUnit): string {
  const at = new Date(bucket)
  if (unit === "hour") {
    return `${at.toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
    })} UTC`
  }
  return `${at.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  })} UTC`
}

export function AlertVolumeChart({
  buckets,
  unit,
}: {
  buckets: readonly AlertBucket[]
  unit: BucketUnit
}) {
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
            dataKey={key}
            fill={`var(--color-${key})`}
            key={key}
            radius={index === ALERT_KEYS.length - 1 ? [4, 4, 0, 0] : 0}
            stackId="alerts"
          />
        ))}
      </BarChart>
    </ChartContainer>
  )
}

export function DecisionVolumeChart({
  buckets,
  unit,
}: {
  buckets: readonly DecisionBucket[]
  unit: BucketUnit
}) {
  const data = buckets.map((entry) => ({ ...entry, label: tickLabel(entry.bucket, unit) }))
  return (
    <ChartContainer className={CHART_CLASS} config={DECISION_CONFIG}>
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
        {DECISION_KEYS.map((key, index) => (
          <Bar
            dataKey={key}
            fill={`var(--color-${key})`}
            key={key}
            radius={index === DECISION_KEYS.length - 1 ? [4, 4, 0, 0] : 0}
            stackId="decisions"
          />
        ))}
      </BarChart>
    </ChartContainer>
  )
}
