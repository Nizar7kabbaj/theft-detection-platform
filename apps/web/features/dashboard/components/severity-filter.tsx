"use client"
import type { Route } from "next"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback } from "react"
import { type AlertSeverity, SEVERITY_VALUES } from "@/features/alerts/api/alert-keys"

const SELECT_CLASS =
  "h-7 rounded-sm border border-border bg-background px-2 font-mono text-[10px] text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50"

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  SEVERITY_UNSPECIFIED: "unspecified",
  SEVERITY_INFO: "info",
  SEVERITY_NOTICE: "notice",
  SEVERITY_WARNING: "warning",
  SEVERITY_CRITICAL: "critical",
}

export function SeverityFilter({ severity }: { severity: AlertSeverity | null }) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const apply = useCallback(
    (value: string) => {
      const next = new URLSearchParams(searchParams.toString())
      if (value === "") {
        next.delete("severity")
      } else {
        next.set("severity", value)
      }
      const query = next.toString()
      router.replace((query === "" ? pathname : `${pathname}?${query}`) as Route)
    },
    [pathname, router, searchParams],
  )

  return (
    <select
      aria-label="filter by severity"
      className={SELECT_CLASS}
      onChange={(event) => {
        apply(event.target.value)
      }}
      value={severity ?? ""}
    >
      <option value="">all severities</option>
      {SEVERITY_VALUES.map((value) => (
        <option key={value} value={value}>
          {SEVERITY_LABEL[value]}
        </option>
      ))}
    </select>
  )
}
