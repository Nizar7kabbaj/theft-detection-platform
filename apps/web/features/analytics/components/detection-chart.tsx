"use client"

import { Bar, BarChart, CartesianGrid, XAxis } from "recharts"
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"

const chartData = [
  { hour: "08", detections: 4 },
  { hour: "10", detections: 9 },
  { hour: "12", detections: 17 },
  { hour: "14", detections: 12 },
  { hour: "16", detections: 21 },
  { hour: "18", detections: 8 },
]

const chartConfig = {
  detections: {
    label: "detections",
    color: "var(--chart-1)",
  },
} satisfies ChartConfig

export function DetectionChart() {
  return (
    <ChartContainer config={chartConfig} className="h-64 w-full">
      <BarChart data={chartData}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="hour" tickLine={false} axisLine={false} tickMargin={8} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="detections" fill="var(--color-detections)" radius={4} />
      </BarChart>
    </ChartContainer>
  )
}
