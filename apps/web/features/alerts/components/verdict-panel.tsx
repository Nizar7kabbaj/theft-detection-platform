import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { classifierStateLabel } from "@/features/alerts/lib/format"

const LABEL_CLASS = "font-mono text-[10px] text-muted-foreground uppercase tracking-[0.16em]"
const NOTE_CLASS = "font-mono text-muted-foreground text-xs"

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
        <p className={LABEL_CLASS}>secondary opinion</p>
        <CardTitle className="text-lg">classifier</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {hasScore || hasState ? (
          <>
            <p className="font-mono text-foreground text-sm tabular-nums">
              {hasScore ? score.toFixed(3) : "no score"}
              {hasState ? ` · ${classifierStateLabel(state)}` : ""}
            </p>
            <p className={NOTE_CLASS}>did not fire this alert, carries no weight alone</p>
          </>
        ) : (
          <p className={NOTE_CLASS}>classifier score not available for this alert</p>
        )}
      </CardContent>
    </Card>
  )
}
