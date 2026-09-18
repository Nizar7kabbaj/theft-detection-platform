import { Card } from "@/components/ui/card"
import type { RankedRow } from "@/features/analytics/components/ranked-list"
import { barWidth, share } from "@/features/analytics/lib/bar-scale"

const TONE: Record<RankedRow["tone"], string> = {
  critical: "bg-destructive",
  warning: "bg-warning",
  info: "bg-info",
  neutral: "bg-muted-foreground/50",
}

const EYEBROW = "font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground"

function rank(index: number): string {
  return `[${String(index).padStart(2, "0")}]`
}

export function LaneList({
  eyebrow,
  title,
  rows,
  total,
  empty,
}: {
  eyebrow: string
  title: string
  rows: readonly RankedRow[]
  total: number
  empty: string
}) {
  return (
    <Card className="gap-4 p-5">
      <p className={EYEBROW}>{eyebrow}</p>
      <h2 className="font-medium text-base text-foreground">{title}</h2>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-muted-foreground text-xs">{empty}</p>
      ) : (
        <ol className="flex flex-col gap-4">
          {rows.map((row, index) => (
            <li
              className={row.muted ? "flex flex-col gap-1.5 opacity-60" : "flex flex-col gap-1.5"}
              key={row.key}
            >
              <div className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={`size-2 shrink-0 rounded-full ${TONE[row.tone]}`}
                />
                <span className="min-w-0 flex-1 truncate font-medium text-foreground text-sm">
                  <span className="mr-1.5 font-mono text-muted-foreground">{rank(index)}</span>
                  {row.label}
                </span>
                <span className="font-mono font-semibold text-foreground text-sm tabular-nums">
                  {row.count}
                </span>
              </div>
              {row.note === null ? null : (
                <p className="pl-4 text-muted-foreground text-xs">{row.note}</p>
              )}
              <div className="flex items-center gap-3 pl-4">
                <div className="h-1.5 flex-1 rounded-full bg-foreground/10">
                  <div
                    className={`h-1.5 rounded-full ${TONE[row.tone]} ${barWidth(row.count, total)}`}
                  />
                </div>
                <span className="w-9 shrink-0 text-right font-mono text-[10px] text-muted-foreground tabular-nums">
                  {share(row.count, total)}
                </span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}
