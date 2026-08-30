import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react"
import type { Route } from "next"
import Link from "next/link"

const LINK_CLASS =
  "inline-flex h-8 items-center gap-1.5 rounded-md px-2 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors"
const ACTIVE_CLASS = `${LINK_CLASS} text-muted-foreground hover:bg-muted hover:text-foreground`
const DISABLED_CLASS = `${LINK_CLASS} text-muted-foreground/40`

export function DetailNav({
  backHref,
  nextHref,
  previousHref,
}: {
  backHref: Route
  nextHref: Route | null
  previousHref: Route | null
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <Link className={ACTIVE_CLASS} href={backHref}>
        <ArrowLeft className="size-3.5" />
        back to alerts
      </Link>
      <div className="flex items-center gap-1">
        {previousHref === null ? (
          <span className={DISABLED_CLASS}>
            <ChevronLeft className="size-3.5" />
            previous
          </span>
        ) : (
          <Link className={ACTIVE_CLASS} href={previousHref}>
            <ChevronLeft className="size-3.5" />
            previous
          </Link>
        )}
        {nextHref === null ? (
          <span className={DISABLED_CLASS}>
            next
            <ChevronRight className="size-3.5" />
          </span>
        ) : (
          <Link className={ACTIVE_CLASS} href={nextHref}>
            next
            <ChevronRight className="size-3.5" />
          </Link>
        )}
      </div>
    </div>
  )
}
