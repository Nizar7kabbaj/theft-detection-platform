"use client"
import { usePathname } from "next/navigation"

const SEGMENT_LABEL: Record<string, string> = {
  dashboard: "dashboard",
  alerts: "alerts",
  cameras: "cameras",
}

export function Breadcrumb() {
  const pathname = usePathname()
  const segments = pathname.split("/").filter((segment) => segment.length > 0)

  if (segments.length === 0) {
    return null
  }

  return (
    <nav aria-label="breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 items-center gap-1.5 text-sm">
        {segments.map((segment, index) => {
          const last = index === segments.length - 1
          const label = SEGMENT_LABEL[segment] ?? segment
          return (
            <li key={segment} className="flex min-w-0 items-center gap-1.5">
              {index === 0 ? null : (
                <span aria-hidden="true" className="text-muted-foreground">
                  /
                </span>
              )}
              <span
                aria-current={last ? "page" : undefined}
                className={last ? "truncate text-foreground" : "truncate text-muted-foreground"}
              >
                {label}
              </span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
