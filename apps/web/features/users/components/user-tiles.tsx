import { Card } from "@/components/ui/card"
import type { UserCounts } from "@/features/users/schemas/user"

function Tile({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <Card className="flex flex-col gap-2 p-4">
      <span className="text-[11px] text-muted-foreground uppercase tracking-widest">{label}</span>
      <span className="font-mono text-3xl text-foreground tabular-nums">
        {String(value).padStart(2, "0")}
      </span>
      <span className="text-muted-foreground text-xs">{note}</span>
    </Card>
  )
}

export function UserTiles({ counts }: { counts: UserCounts }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Tile label="total users" value={counts.total} note="accounts on this platform" />
      <Tile label="active" value={counts.active} note="able to sign in" />
      <Tile label="disabled" value={counts.disabled} note="sign-in refused" />
      <Tile label="live sessions" value={counts.live_sessions} note="not yet revoked" />
    </div>
  )
}
