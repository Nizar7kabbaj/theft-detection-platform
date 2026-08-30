"use client"
import dynamic from "next/dynamic"
import { useState } from "react"
import { Card } from "@/components/ui/card"
import type { SeverityField } from "@/features/analytics/components/severity-radial"
import type { AlertBucket } from "@/features/analytics/schemas/timeseries"

const Radial = dynamic(
  () => import("@/features/analytics/components/severity-radial").then((m) => m.SeverityRadial),
  {
    ssr: false,
    loading: () => (
      <div className="mx-auto aspect-square w-full max-w-64 animate-pulse rounded-full bg-muted" />
    ),
  },
)

const ORDER: readonly SeverityField[] = ["critical", "warning", "notice", "info", "unspecified"]

const SWATCH: Record<SeverityField, string> = {
  critical: "bg-chart-4",
  warning: "bg-chart-1",
  notice: "bg-chart-2",
  info: "bg-chart-3",
  unspecified: "bg-chart-5",
}

const EYEBROW = "font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
const CHIP =
  "inline-flex h-7 items-center gap-2 rounded-sm border border-border px-2.5 font-mono text-[10px] uppercase tracking-wide outline-none transition-[background-color,color,opacity] duration-150 focus-visible:ring-2 focus-visible:ring-ring/40"
const CHIP_ON = "bg-accent text-foreground"
const CHIP_OFF = "text-muted-foreground opacity-50 hover:opacity-80"

function sum(buckets: readonly AlertBucket[], field: SeverityField): number {
  return buckets.reduce((total, bucket) => total + bucket[field], 0)
}

export function SeverityPanel({ buckets }: { buckets: readonly AlertBucket[] }) {
  const present = ORDER.filter((field) => sum(buckets, field) > 0)
  const [hidden, setHidden] = useState<readonly SeverityField[]>([])
  const shown = present.filter((field) => !hidden.includes(field))
  const rows = shown.map((field) => ({ field, count: sum(buckets, field) }))
  const total = rows.reduce((count, row) => count + row.count, 0)

  const toggle = (field: SeverityField) => {
    setHidden((current) =>
      current.includes(field) ? current.filter((entry) => entry !== field) : [...current, field],
    )
  }

  return (
    <Card className="gap-5 p-5">
      <div className="flex flex-col gap-1">
        <p className={EYEBROW}>severity spread</p>
        <h2 className="font-medium text-base text-foreground">events by level</h2>
      </div>
      {present.length === 0 ? (
        <p className="py-10 text-center text-muted-foreground text-xs">
          no alerts were raised in this window
        </p>
      ) : (
        <>
          {rows.length === 0 ? (
            <p className="py-10 text-center text-muted-foreground text-xs">every level is hidden</p>
          ) : (
            <Radial rows={rows} />
          )}
          <fieldset className="flex flex-wrap gap-2">
            <legend className="sr-only">show or hide a severity level</legend>
            {present.map((field) => {
              const on = !hidden.includes(field)
              return (
                <button
                  aria-pressed={on}
                  className={`${CHIP} ${on ? CHIP_ON : CHIP_OFF}`}
                  key={field}
                  onClick={() => toggle(field)}
                  type="button"
                >
                  <span className={`size-2 shrink-0 rounded-full ${SWATCH[field]}`} />
                  {field}
                  <span className="text-foreground tabular-nums">{sum(buckets, field)}</span>
                </button>
              )
            })}
          </fieldset>
        </>
      )}
      <p className="text-[11px] text-muted-foreground">
        {total} events shown of {buckets.reduce((count, bucket) => count + bucket.total, 0)} in this
        window
      </p>
    </Card>
  )
}
