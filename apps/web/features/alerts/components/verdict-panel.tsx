import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { classifierStateLabel } from "@/features/alerts/lib/format"

const ROW_CLASS = "flex items-baseline justify-between gap-4 py-1"
const LABEL_CLASS = "text-muted-foreground text-sm"
const VALUE_CLASS = "text-foreground text-sm tabular-nums"

export function VerdictPanel({
  score,
  state,
}: {
  score: number | null | undefined
  state: string | null | undefined
}) {
  const hasScore = score !== null && score !== undefined
  const hasState = state !== null && state !== undefined

  return (
    <Card>
      <CardHeader>
        <CardTitle>second opinion</CardTitle>
        <CardDescription>
          the motion classifier scored this sequence. it did not fire the alert, and it is wrong
          often enough that it carries no weight on its own
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl>
          <div className={ROW_CLASS}>
            <dt className={LABEL_CLASS}>score</dt>
            <dd className={hasScore ? VALUE_CLASS : LABEL_CLASS}>
              {hasScore ? score.toFixed(3) : "not scored"}
            </dd>
          </div>
          <div className={ROW_CLASS}>
            <dt className={LABEL_CLASS}>state</dt>
            <dd className={hasState ? VALUE_CLASS : LABEL_CLASS}>
              {hasState ? classifierStateLabel(state) : "no state recorded"}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  )
}
