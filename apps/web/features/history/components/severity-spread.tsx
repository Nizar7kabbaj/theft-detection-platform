import { Card } from "@/components/ui/card"
import type { SeverityTally } from "@/features/history/api/archive-summary"

const WIDTH: Record<number, string> = {
  0: "w-0",
  1: "w-[10%]",
  2: "w-[20%]",
  3: "w-[30%]",
  4: "w-[40%]",
  5: "w-1/2",
  6: "w-[60%]",
  7: "w-[70%]",
  8: "w-[80%]",
  9: "w-[90%]",
  10: "w-full",
}

const ROWS: readonly (readonly [keyof SeverityTally, string])[] = [
  ["critical", "bg-destructive"],
  ["warning", "bg-warning"],
  ["notice", "bg-info"],
  ["info", "bg-muted-foreground/50"],
]

function widthClass(value: number, peak: number): string {
  if (peak <= 0 || value <= 0) {
    return WIDTH[0] as string
  }
  const step = Math.max(1, Math.round((value / peak) * 10))
  return (WIDTH[step] ?? WIDTH[10]) as string
}

export function SeveritySpread({ tally }: { tally: SeverityTally }) {
  const peak = Math.max(tally.critical, tally.warning, tally.notice, tally.info)
  return (
    <Card className="flex flex-col gap-4 p-5">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
        severity spread
      </p>
      <h2 className="font-medium text-base text-foreground">events by level</h2>
      <dl className="flex flex-col gap-3">
        {ROWS.map(([key, color]) => (
          <div className="flex flex-col gap-1.5" key={key}>
            <div className="flex items-baseline justify-between">
              <dt className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                {key}
              </dt>
              <dd className="text-foreground text-sm tabular-nums">{tally[key]}</dd>
            </div>
            <div className="h-1 rounded-full bg-foreground/10">
              <div className={`h-1 rounded-full ${color} ${widthClass(tally[key], peak)}`} />
            </div>
          </div>
        ))}
      </dl>
    </Card>
  )
}
