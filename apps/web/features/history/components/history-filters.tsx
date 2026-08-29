"use client"

import type { Route } from "next"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback } from "react"
import { Button } from "@/components/ui/button"
import { SEVERITY_VALUES } from "@/features/alerts/api/alert-keys"
import { DECISION_LABEL, SEVERITY_LABEL } from "@/features/alerts/lib/format"
import {
  HISTORY_FILTERS_COOKIE_MAX_AGE,
  HISTORY_FILTERS_COOKIE_NAME,
  serializeFilters,
} from "@/features/history/api/history-cookie"
import {
  DECISION_VALUES,
  DEFAULT_RANGE,
  DEFAULT_SORT,
  type HistoryFilters,
  type HistoryRange,
  parseHistoryFilters,
  RANGE_VALUES,
  SORT_VALUES,
} from "@/features/history/api/history-keys"
import { writeCookie } from "@/lib/cookies/write"

const SELECT_CLASS =
  "h-8 rounded-lg border border-border bg-background px-2 text-sm text-foreground outline-none transition-[border-color,box-shadow] duration-150 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
const LABEL_CLASS = "flex items-center gap-2 text-muted-foreground text-sm"
const RANGE_BASE =
  "h-8 rounded-md px-3 font-mono text-[11px] uppercase tracking-wide outline-none transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring"
const RANGE_ON = "bg-foreground/10 text-foreground"
const RANGE_OFF = "text-muted-foreground hover:text-foreground"

const RANGE_LABEL: Record<HistoryRange, string> = {
  today: "today",
  "7d": "7 days",
  "30d": "30 days",
}

const SORT_LABEL: Record<(typeof SORT_VALUES)[number], string> = {
  decided_at: "decision time",
  created_at: "alert time",
}

function activeCount(filters: HistoryFilters): number {
  let count = 0
  if (filters.range !== DEFAULT_RANGE) {
    count += 1
  }
  if (filters.sort !== DEFAULT_SORT) {
    count += 1
  }
  if (filters.decision !== null) {
    count += 1
  }
  if (filters.severity !== null) {
    count += 1
  }
  if (filters.camera !== null) {
    count += 1
  }
  return count
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
      const raw: Record<string, string> = {}
      next.forEach((entry, key) => {
        raw[key] = entry
      })
      writeCookie(
        HISTORY_FILTERS_COOKIE_NAME,
        serializeFilters(parseHistoryFilters(raw)),
        HISTORY_FILTERS_COOKIE_MAX_AGE,
      )
      const query = next.toString()
      router.replace((query === "" ? pathname : `${pathname}?${query}`) as Route)
    },
    [pathname, router, searchParams],
  )

  const clear = useCallback(() => {
    writeCookie(HISTORY_FILTERS_COOKIE_NAME, "", 0)
    router.replace("/history" as Route)
  }, [router])

  const selected = filters.camera
  const known = selected === null || cameras.some(([id]) => id === selected)
  const active = activeCount(filters)

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
      <fieldset className="flex items-center gap-1">
        <legend className="sr-only">time range</legend>
        {RANGE_VALUES.map((value) => (
          <button
            aria-pressed={filters.range === value}
            className={`${RANGE_BASE} ${filters.range === value ? RANGE_ON : RANGE_OFF}`}
            key={value}
            onClick={() => apply("range", value)}
            type="button"
          >
            {RANGE_LABEL[value]}
          </button>
        ))}
      </fieldset>

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

      {active > 0 ? (
        <Button onClick={clear} size="xs" variant="ghost">
          clear filters
          <span className="ml-1.5 rounded-sm bg-foreground/10 px-1 font-mono text-[10px] tabular-nums">
            {active}
          </span>
        </Button>
      ) : null}
    </div>
  )
}
