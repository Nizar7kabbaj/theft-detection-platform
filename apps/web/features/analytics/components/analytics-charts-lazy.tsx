"use client"
import dynamic from "next/dynamic"
import type {
  AlertBucket,
  BucketUnit,
  DecisionBucket,
} from "@/features/analytics/schemas/timeseries"

const SKELETON_CLASS = "h-64 w-full animate-pulse rounded-sm bg-muted motion-reduce:animate-none"

const AlertChart = dynamic(
  () => import("@/features/analytics/components/analytics-charts").then((m) => m.AlertVolumeChart),
  {
    ssr: false,
    loading: () => <div className={SKELETON_CLASS} />,
  },
)

const Throughput = dynamic(
  () => import("@/features/analytics/components/analytics-charts").then((m) => m.ThroughputChart),
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

export function ThroughputChartLazy({
  alerts,
  decisions,
  unit,
}: {
  alerts: readonly AlertBucket[]
  decisions: readonly DecisionBucket[]
  unit: BucketUnit
}) {
  return <Throughput alerts={alerts} decisions={decisions} unit={unit} />
}
