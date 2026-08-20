import type { Route } from "next"
import Link from "next/link"
import { type HistoryFilters, historyHref } from "@/features/history/api/history-keys"

const LINK_CLASS =
  "inline-flex h-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background px-2.5 font-medium text-sm outline-none transition-colors duration-150 hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

export function HistoryPager({
  filters,
  cursor,
  nextCursor,
  count,
}: {
  filters: HistoryFilters
  cursor: string | null
  nextCursor: string | null
  count: number
}) {
  if (cursor === null && nextCursor === null) {
    return null
  }
  return (
    <nav aria-label="history pages" className="flex items-center gap-3">
      {cursor === null ? null : (
        <Link className={LINK_CLASS} href={historyHref(filters, null) as Route}>
          first page
        </Link>
      )}
      <p className="text-muted-foreground text-sm tabular-nums">{count} on this page</p>
      {nextCursor === null ? null : (
        <Link className={LINK_CLASS} href={historyHref(filters, nextCursor) as Route}>
          next page
        </Link>
      )}
    </nav>
  )
}
