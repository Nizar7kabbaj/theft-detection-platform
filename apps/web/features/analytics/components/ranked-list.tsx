import { Card } from "@/components/ui/card"
import { barWidth, share } from "@/features/analytics/lib/bar-scale"

export type RankedRow = {
  key: string
  label: string
  count: number
  tone: "critical" | "warning" | "info" | "neutral"
  muted: boolean
  note: string | null
}

const TONE: Record<RankedRow["tone"], string> = {
  critical: "bg-destructive",
  warning: "bg-warning",
  info: "bg-info",
  neutral: "bg-muted-foreground/50",
}

const EYEBROW = "font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
const LABEL = "min-w-0 flex-1 truncate font-mono text-[11px] uppercase tracking-wide"

export function RankedList({
  eyebrow,
  title,
  rows,
  total,
  empty,
  showShare,
}: {
  eyebrow: string
  title: string
  rows: readonly RankedRow[]
  total: number
  empty: string
  showShare: boolean
}) {
  const peak = rows.length === 0 ? 0 : Math.max(...rows.map((row) => row.count))
  return (
    <Card className="gap-4 p-5">
      <p className={EYEBROW}>{eyebrow}</p>
      <h2 className="font-medium text-base text-foreground">{title}</h2>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-muted-foreground text-xs">{empty}</p>
      ) : (
        <dl className="flex flex-col gap-3.5">
          {rows.map((row) => (
            <div className="flex items-center gap-4" key={row.key}>
              <dt
                className={
                  row.muted ? `${LABEL} text-muted-foreground/60` : `${LABEL} text-muted-foreground`
                }
              >
                {row.label}
                {row.note === null ? null : (
                  <span className="ml-1.5 text-muted-foreground/50">· {row.note}</span>
                )}
              </dt>
              <div className="h-1.5 w-1/2 shrink-0 rounded-full bg-foreground/10">
                <div
                  className={`h-1.5 rounded-full ${TONE[row.tone]} ${barWidth(row.count, peak)} ${
                    row.muted ? "opacity-50" : ""
                  }`}
                />
              </div>
              <dd className="w-20 shrink-0 text-right font-mono text-foreground text-xs tabular-nums">
                {row.count}
                {showShare ? (
                  <span className="ml-1.5 text-muted-foreground">· {share(row.count, total)}</span>
                ) : null}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  )
}
