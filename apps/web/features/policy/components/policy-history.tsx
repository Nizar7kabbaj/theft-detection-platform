import { Card } from "@/components/ui/card"
import { formatUnit, shortTime } from "@/features/policy/lib/format"
import { FIELD_LABELS, FIELD_UNITS, type PolicyRevision } from "@/features/policy/schemas/policy"

const CELL = "px-3 py-2 text-left font-normal"

export function PolicyHistory({ revisions }: { revisions: readonly PolicyRevision[] }) {
  return (
    <Card className="flex flex-col gap-1 p-4">
      <span className="text-[10px] text-muted-foreground uppercase tracking-widest">
        change history
      </span>
      <span className="mb-2 text-foreground text-lg">every change is signed</span>
      {revisions.length === 0 ? (
        <div className="rounded-lg border border-border border-dashed py-8 text-center text-muted-foreground text-sm">
          no change recorded yet
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-muted/40">
              <tr className="text-[10px] text-muted-foreground uppercase tracking-widest">
                <th className={CELL}>version</th>
                <th className={CELL}>when</th>
                <th className={CELL}>field</th>
                <th className={CELL}>change</th>
              </tr>
            </thead>
            <tbody>
              {revisions.flatMap((revision) =>
                revision.changes.map((change) => (
                  <tr
                    key={`${revision.version}-${change.field_name}`}
                    className="border-border/60 border-t"
                  >
                    <td className={`${CELL} font-mono text-muted-foreground text-xs tabular-nums`}>
                      {revision.version}
                    </td>
                    <td className={`${CELL} font-mono text-muted-foreground text-xs tabular-nums`}>
                      {shortTime(revision.changed_at)}
                    </td>
                    <td className={`${CELL} text-foreground`}>
                      {FIELD_LABELS.get(change.field_name) ?? change.field_name}
                    </td>
                    <td className={`${CELL} font-mono text-xs tabular-nums`}>
                      <span className="text-muted-foreground">
                        {formatUnit(change.previous, FIELD_UNITS.get(change.field_name) ?? "ratio")}
                      </span>
                      <span className="text-muted-foreground"> to </span>
                      <span className="text-foreground">
                        {formatUnit(change.current, FIELD_UNITS.get(change.field_name) ?? "ratio")}
                      </span>
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
