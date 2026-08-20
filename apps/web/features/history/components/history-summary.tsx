import { DECISION_LABEL } from "@/features/alerts/lib/format"
import type { Alert, Decision } from "@/features/alerts/schemas/alert"

const COUNTED: readonly Decision[] = [
  "DECISION_CONFIRMED",
  "DECISION_DISMISSED",
  "DECISION_UNSURE",
  "DECISION_UNSPECIFIED",
]

const TERM_CLASS = "text-muted-foreground text-xs"
const VALUE_CLASS = "font-semibold text-foreground text-lg tabular-nums"

export function HistorySummary({ rows }: { rows: readonly Alert[] }) {
  if (rows.length === 0) {
    return null
  }
  const tally = new Map<Decision, number>()
  for (const alert of rows) {
    tally.set(alert.decision, (tally.get(alert.decision) ?? 0) + 1)
  }
  return (
    <dl className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-xl px-4 py-3 ring-1 ring-foreground/10">
      {COUNTED.map((decision) => (
        <div className="flex flex-col gap-0.5" key={decision}>
          <dt className={TERM_CLASS}>{DECISION_LABEL[decision]}</dt>
          <dd className={VALUE_CLASS}>{tally.get(decision) ?? 0}</dd>
        </div>
      ))}
      <p className="ml-auto text-muted-foreground text-xs">counted on this page only</p>
    </dl>
  )
}
