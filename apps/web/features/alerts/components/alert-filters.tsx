"use client"
import type { Route } from "next"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback } from "react"
import {
  type AlertFilters,
  type AlertSeverity,
  SEVERITY_VALUES,
} from "@/features/alerts/api/alert-keys"

const SELECT_CLASS =
  "h-8 rounded-lg border border-border bg-background px-2 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  SEVERITY_UNSPECIFIED: "unspecified",
  SEVERITY_INFO: "info",
  SEVERITY_NOTICE: "notice",
  SEVERITY_WARNING: "warning",
  SEVERITY_CRITICAL: "critical",
}

export function AlertFilterControls({ filters }: { filters: AlertFilters }) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const apply = useCallback(
    (name: string, value: string) => {
      const next = new URLSearchParams(searchParams.toString())
      if (value === "") {
        next.delete(name)
      } else {
        next.set(name, value)
      }
      const query = next.toString()
      router.replace((query === "" ? pathname : `${pathname}?${query}`) as Route)
    },
    [pathname, router, searchParams],
  )

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="flex items-center gap-2 text-muted-foreground text-sm" htmlFor="severity">
        severity
        <select
          className={SELECT_CLASS}
          id="severity"
          name="severity"
          onChange={(event) => apply("severity", event.target.value)}
          value={filters.severity ?? ""}
        >
          <option value="">all</option>
          {SEVERITY_VALUES.map((value) => (
            <option key={value} value={value}>
              {SEVERITY_LABEL[value]}
            </option>
          ))}
        </select>
      </label>
      <label
        className="flex items-center gap-2 text-muted-foreground text-sm"
        htmlFor="acknowledged"
      >
        state
        <select
          className={SELECT_CLASS}
          id="acknowledged"
          name="acknowledged"
          onChange={(event) => apply("acknowledged", event.target.value)}
          value={filters.acknowledged === null ? "" : String(filters.acknowledged)}
        >
          <option value="">all</option>
          <option value="false">open</option>
          <option value="true">acknowledged</option>
        </select>
      </label>
    </div>
  )
}
