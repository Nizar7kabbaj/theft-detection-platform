"use client"
import { Cell, Pie, PieChart } from "recharts"
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import type { AlertBucket } from "@/features/analytics/schemas/timeseries"

export type SeverityField = Exclude<keyof AlertBucket, "bucket" | "total">

export const SEVERITY_CONFIG = {
  critical: { label: "critical", color: "var(--chart-4)" },
  warning: { label: "warning", color: "var(--chart-1)" },
  notice: { label: "notice", color: "var(--chart-2)" },
  info: { label: "info", color: "var(--chart-3)" },
  unspecified: { label: "unspecified", color: "var(--chart-5)" },
} as const satisfies ChartConfig

export function SeverityRadial({
  rows,
}: {
  rows: readonly { field: SeverityField; count: number }[]
}) {
  const data = rows.map((row) => ({ field: row.field, value: row.count }))
  const total = rows.reduce((count, row) => count + row.count, 0)
  return (
    <ChartContainer className="mx-auto aspect-square w-full max-w-64" config={SEVERITY_CONFIG}>
      <PieChart>
        <ChartTooltip content={<ChartTooltipContent hideLabel={true} nameKey="field" />} />
        <Pie
          cornerRadius={4}
          data={data}
          dataKey="value"
          endAngle={-270}
          innerRadius="62%"
          isAnimationActive={false}
          nameKey="field"
          outerRadius="100%"
          paddingAngle={2}
          startAngle={90}
          strokeWidth={0}
        >
          {data.map((entry) => (
            <Cell fill={`var(--color-${entry.field})`} key={entry.field} />
          ))}
        </Pie>
        <text dominantBaseline="middle" textAnchor="middle" x="50%" y="50%">
          <tspan
            className="fill-foreground font-mono tabular-nums"
            dy="-0.2em"
            fontSize={26}
            x="50%"
          >
            {total}
          </tspan>
          <tspan
            className="fill-muted-foreground font-mono uppercase"
            dy="1.6em"
            fontSize={9}
            x="50%"
          >
            events
          </tspan>
        </text>
      </PieChart>
    </ChartContainer>
  )
}
