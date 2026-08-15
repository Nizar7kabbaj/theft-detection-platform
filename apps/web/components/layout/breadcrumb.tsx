"use client"

import { usePathname } from "next/navigation"

const SEGMENT_LABEL: Record<string, string> = {
  dashboard: "dashboard",
  alerts: "alerts",
  cameras: "cameras",
  history: "history",
  analytics: "analytics",
  settings: "settings",
}

const CRUMB_LIST_CLASS = "flex min-w-0 items-center gap-1.5 text-[0.8125rem]/5"

export function Breadcrumb() {
  const pathname = usePathname()
  const segments = pathname.split("/").filter((segment) => segment.length > 0)

  if (segments.length === 0) {
    return null
  }

  return (
    <nav aria-label="breadcrumb" className="min-w-0">
      <ol className={CRUMB_LIST_CLASS}>
        {segments.map((segment, index) => {
          const last = index === segments.length - 1
          const label = SEGMENT_LABEL[segment] ?? segment
          return (
            <li key={segment} className="flex min-w-0 items-center gap-1.5">
              {index === 0 ? null : (
                <span aria-hidden="true" className="text-muted-foreground/60">
                  /
                </span>
              )}
              <span
                aria-current={last ? "page" : undefined}
                className={
                  last ? "truncate font-medium text-foreground" : "truncate text-muted-foreground"
                }
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
