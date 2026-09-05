const NOTICES = new Map<string, string>([
  ["session_ended", "your session ended, sign in again to continue"],
  ["signed_out", "you were signed out"],
])

export function SessionNotice({ reason }: { reason: string | undefined }) {
  if (reason === undefined) {
    return null
  }
  const message = NOTICES.get(reason)
  if (message === undefined) {
    return null
  }
  return (
    <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-muted-foreground text-sm">
      {message}
    </p>
  )
}
