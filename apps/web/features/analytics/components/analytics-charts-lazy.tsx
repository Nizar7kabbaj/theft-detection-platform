"use client"
import dynamic from "next/dynamic"
import type {
  AlertBucket,
  BucketUnit,
  DecisionBucket,
} from "@/features/analytics/schemas/timeseries"

const SKELETON_CLASS = "h-64 w-full animate-pulse rounded-lg bg-muted"

const AlertChart = dynamic(
  () => import("@/features/analytics/components/analytics-charts").then((m) => m.AlertVolumeChart),
  {
    ssr: false,
    loading: () => <div className={SKELETON_CLASS} />,
  },
)

const DecisionChart = dynamic(
  () =>
    import("@/features/analytics/components/analytics-charts").then((m) => m.DecisionVolumeChart),
  {
    ssr: false,
    loading: () => <div className={SKELETON_CLASS} />,
  },
)

export function AlertVolumeChartLazy({
  buckets,
  unit,
}: {
  buckets: readonly AlertBucket[]
  unit: BucketUnit
}) {
  return <AlertChart buckets={buckets} unit={unit} />
}

export function DecisionVolumeChartLazy({
  buckets,
  unit,
}: {
  buckets: readonly DecisionBucket[]
  unit: BucketUnit
}) {
  return <DecisionChart buckets={buckets} unit={unit} />
}
