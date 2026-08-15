"use client"
import dynamic from "next/dynamic"

const Chart = dynamic(
  () => import("@/features/analytics/components/detection-chart").then((m) => m.DetectionChart),
  {
    ssr: false,
    loading: () => <div className="h-64 w-full animate-pulse rounded bg-muted" />,
  },
)

export function DetectionChartLazy() {
  return <Chart />
}
