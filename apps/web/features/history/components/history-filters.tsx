"use client"

import type { Route } from "next"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback } from "react"
import { SEVERITY_VALUES } from "@/features/alerts/api/alert-keys"
import { DECISION_LABEL, SEVERITY_LABEL } from "@/features/alerts/lib/format"
import {
  DECISION_VALUES,
  type HistoryFilters,
  SORT_VALUES,
} from "@/features/history/api/history-keys"

const SELECT_CLASS =
  "h-8 rounded-lg border border-border bg-background px-2 text-sm text-foreground outline-none transition-[border-color,box-shadow] duration-150 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
const LABEL_CLASS = "flex items-center gap-2 text-muted-foreground text-sm"

const SORT_LABEL: Record<(typeof SORT_VALUES)[number], string> = {
  decided_at: "decision time",
  created_at: "alert time",
}

export function HistoryFilterControls({
  filters,
  cameras,
}: {
  filters: HistoryFilters
  cameras: readonly (readonly [string, string])[]
}) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const apply = useCallback(
    (name: string, value: string) => {
      const next = new URLSearchParams(searchParams.toString())
      next.delete("cursor")
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

  const selected = filters.camera
  const known = selected === null || cameras.some(([id]) => id === selected)

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
      <label className={LABEL_CLASS} htmlFor="decision">
        decision
        <select
          className={SELECT_CLASS}
          id="decision"
          name="decision"
          onChange={(event) => apply("decision", event.target.value)}
          value={filters.decision ?? ""}
        >
          <option value="">all</option>
          {DECISION_VALUES.map((value) => (
            <option key={value} value={value}>
              {DECISION_LABEL[value]}
            </option>
          ))}
        </select>
      </label>
      <label className={LABEL_CLASS} htmlFor="severity">
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
      {cameras.length > 0 ? (
        <label className={LABEL_CLASS} htmlFor="camera_id">
          camera
          <select
            className={SELECT_CLASS}
            id="camera_id"
            name="camera_id"
            onChange={(event) => apply("camera_id", event.target.value)}
            value={selected ?? ""}
          >
            <option value="">all</option>
            {cameras.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
            {known ? null : (
              <option key={selected} value={selected ?? ""}>
                {selected} (not registered)
              </option>
            )}
          </select>
        </label>
      ) : null}
      <label className={LABEL_CLASS} htmlFor="sort">
        ordered by
        <select
          className={SELECT_CLASS}
          id="sort"
          name="sort"
          onChange={(event) => apply("sort", event.target.value)}
          value={filters.sort}
        >
          {SORT_VALUES.map((value) => (
            <option key={value} value={value}>
              {SORT_LABEL[value]}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}
