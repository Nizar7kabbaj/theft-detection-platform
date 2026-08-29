import { Card } from "@/components/ui/card"
import type { Decision } from "@/features/alerts/schemas/alert"
import type { ArchiveSummary } from "@/features/history/api/archive-summary"

const EYEBROW = "font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
const BIG = "font-semibold text-3xl text-foreground tabular-nums"
const FOOT = "flex items-center justify-between border-border/60 border-t pt-3"

const WIDTH: Record<number, string> = {
  0: "w-0",
  5: "w-[5%]",
  10: "w-[10%]",
  15: "w-[15%]",
  20: "w-[20%]",
  25: "w-[25%]",
  30: "w-[30%]",
  35: "w-[35%]",
  40: "w-[40%]",
  45: "w-[45%]",
  50: "w-1/2",
  55: "w-[55%]",
  60: "w-[60%]",
  65: "w-[65%]",
  70: "w-[70%]",
  75: "w-3/4",
  80: "w-[80%]",
  85: "w-[85%]",
  90: "w-[90%]",
  95: "w-[95%]",
  100: "w-full",
}

const HEIGHT: Record<number, string> = {
  0: "h-px",
  1: "h-1",
  2: "h-2",
  3: "h-3",
  4: "h-4",
  5: "h-5",
  6: "h-6",
  7: "h-7",
  8: "h-8",
}

const MIX_COLOR: Record<Exclude<Decision, "DECISION_UNSPECIFIED"> | "undecided", string> = {
  DECISION_CONFIRMED: "bg-destructive",
  DECISION_DISMISSED: "bg-muted-foreground/60",
  DECISION_UNSURE: "bg-warning",
  undecided: "bg-foreground/15",
}

function widthClass(part: number, whole: number): string {
  if (whole <= 0) {
    return WIDTH[0] as string
  }
  const step = Math.round((part / whole) * 20) * 5
  return (WIDTH[step] ?? WIDTH[0]) as string
}

function heightClass(value: number, peak: number): string {
  if (peak <= 0 || value <= 0) {
    return HEIGHT[0] as string
  }
  const step = Math.max(1, Math.round((value / peak) * 8))
  return (HEIGHT[step] ?? HEIGHT[8]) as string
}

function percent(part: number, whole: number): string {
  if (whole <= 0) {
    return "0%"
  }
  return `${Math.round((part / whole) * 100)}%`
}

function Sparkline({ volume }: { volume: readonly number[] }) {
  if (volume.length === 0) {
    return <p className="text-muted-foreground text-xs">no buckets in this range</p>
  }
  const peak = Math.max(...volume)
  return (
    <div
      aria-label={`alert volume across ${volume.length} buckets, peak ${peak}`}
      className="flex h-8 items-end gap-0.5"
      role="img"
    >
      {volume.map((value, index) => (
        <span
          className={`flex-1 rounded-[1px] bg-info/70 ${heightClass(value, peak)}`}
          key={`bucket-${String(index)}-${String(value)}`}
        />
      ))}
    </div>
  )
}

export function ArchiveCards({ summary }: { summary: ArchiveSummary }) {
  const mix: readonly (readonly [string, string, number])[] = [
    ["confirmed", MIX_COLOR.DECISION_CONFIRMED, summary.decisions.DECISION_CONFIRMED],
    ["dismissed", MIX_COLOR.DECISION_DISMISSED, summary.decisions.DECISION_DISMISSED],
    ["unsure", MIX_COLOR.DECISION_UNSURE, summary.decisions.DECISION_UNSURE],
    ["undecided", MIX_COLOR.undecided, summary.undecided],
  ]
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="flex flex-col gap-4 p-5">
        <p className={EYEBROW}>archive volume</p>
        <div className="flex flex-col gap-1">
          <p className={BIG}>{summary.total}</p>
          <p className="text-muted-foreground text-sm">alerts in range</p>
        </div>
        <div className="mt-auto flex flex-col gap-1.5">
          <Sparkline volume={summary.volume} />
          <div className="flex justify-between font-mono text-[10px] text-muted-foreground">
            <span>start</span>
            <span>now</span>
          </div>
        </div>
      </Card>

      <Card className="flex flex-col gap-4 p-5">
        <p className={EYEBROW}>review posture</p>
        <div className="flex flex-col gap-1">
          <p className={BIG}>
            {summary.decided}
            <span className="ml-1.5 font-normal text-lg text-muted-foreground/60">
              / {summary.total}
            </span>
          </p>
          <p className="text-muted-foreground text-sm">decided by an operator</p>
        </div>
        <div className={`mt-auto ${FOOT}`}>
          <span className={EYEBROW}>still undecided</span>
          <span className="font-semibold text-foreground text-sm tabular-nums">
            {summary.undecided}
          </span>
        </div>
      </Card>

      <Card className="flex flex-col gap-4 p-5">
        <p className={EYEBROW}>decision mix</p>
        <div className="flex h-2 overflow-hidden rounded-full bg-foreground/10">
          {mix.map(([label, color, value]) => (
            <span className={`${color} ${widthClass(value, summary.total)}`} key={label} />
          ))}
        </div>
        <dl className="mt-auto grid grid-cols-2 gap-x-6 gap-y-2">
          {mix.map(([label, color, value]) => (
            <div className="flex items-center gap-2" key={label}>
              <span className={`size-2 shrink-0 rounded-[2px] ${color}`} />
              <dt className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                {label}
              </dt>
              <dd className="ml-auto text-foreground text-xs tabular-nums">
                {percent(value, summary.total)}
              </dd>
            </div>
          ))}
        </dl>
      </Card>
    </div>
  )
}
