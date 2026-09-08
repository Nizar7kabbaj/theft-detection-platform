"use client"

import { Search } from "lucide-react"
import type { Route } from "next"
import { usePathname, useRouter } from "next/navigation"
import { useCallback, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  ALERT_FILTERS_COOKIE_MAX_AGE,
  ALERT_FILTERS_COOKIE_NAME,
} from "@/features/alerts/api/alert-cookie"
import {
  type AlertFilters,
  type AlertSeverity,
  type AlertSort,
  activeFilterCount,
  alertFiltersToSearch,
  type CameraOption,
  DECISION_VALUES,
  SORT_VALUES,
} from "@/features/alerts/api/alert-keys"
import { civilToday, type RangePreset, serializeRange } from "@/features/alerts/lib/range"
import type { Decision } from "@/features/alerts/schemas/alert"
import { writeCookie } from "@/lib/cookies/write"

const GROUP_LABEL_CLASS = "font-mono text-[10px] text-muted-foreground uppercase tracking-wider"

const LEGEND_CLASS = `mb-2 block ${GROUP_LABEL_CLASS}`

const SELECT_CLASS =
  "h-8 rounded-lg border border-border bg-background px-2 text-foreground text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"

const SEGMENT_WRAP_CLASS = "flex items-center gap-0.5 rounded-lg border border-border p-0.5"

const SEVERITY_SEGMENTS = [
  { value: "", label: "all" },
  { value: "SEVERITY_CRITICAL", label: "critical" },
  { value: "SEVERITY_WARNING", label: "warning" },
  { value: "SEVERITY_NOTICE", label: "notice" },
  { value: "SEVERITY_INFO", label: "info" },
] as const satisfies readonly { value: AlertSeverity | ""; label: string }[]

const RANGE_SEGMENTS = [
  { value: "", label: "any time" },
  { value: "today", label: "today" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "90d", label: "90 days" },
] as const satisfies readonly { value: RangePreset | ""; label: string }[]
const STATE_SEGMENTS = [
  { value: "", label: "all" },
  { value: "false", label: "open" },
  { value: "true", label: "acknowledged" },
] as const satisfies readonly { value: string; label: string }[]

const DECISION_LABEL: Record<Decision, string> = {
  DECISION_UNSPECIFIED: "no decision",
  DECISION_CONFIRMED: "confirmed",
  DECISION_DISMISSED: "dismissed",
  DECISION_UNSURE: "unsure",
}

const SORT_LABEL: Record<AlertSort, string> = {
  created_at: "order by received",
  decided_at: "order by decided",
}

function Segmented({
  legend,
  segments,
  current,
  onSelect,
}: {
  legend: string
  segments: readonly { value: string; label: string }[]
  current: string
  onSelect: (value: string) => void
}) {
  return (
    <fieldset>
      <legend className={LEGEND_CLASS}>{legend}</legend>
      <div className={SEGMENT_WRAP_CLASS}>
        {segments.map((segment) => (
          <Button
            aria-pressed={segment.value === current}
            className="font-mono text-[11px] uppercase tracking-wide"
            key={segment.value}
            onClick={() => onSelect(segment.value)}
            size="xs"
            variant={segment.value === current ? "secondary" : "ghost"}
          >
            {segment.label}
          </Button>
        ))}
      </div>
    </fieldset>
  )
}

export function AlertFilterControls({
  filters,
  cameras,
  text,
  onTextChange,
  onReset,
}: {
  filters: AlertFilters
  cameras: CameraOption[]
  text: string
  onTextChange: (value: string) => void
  onReset: () => void
}) {
  const router = useRouter()
  const pathname = usePathname()
  const active = activeFilterCount(filters)
  const incoming =
    filters.range !== null && typeof filters.range !== "string"
      ? filters.range
      : { from: "", to: "" }
  const marker = filters.range === null ? "" : serializeRange(filters.range)
  const [custom, setCustom] = useState(incoming)
  const [seen, setSeen] = useState(marker)
  if (marker !== seen) {
    setSeen(marker)
    setCustom(incoming)
  }

  const apply = useCallback(
    (name: string, value: string) => {
      const next = new URLSearchParams(alertFiltersToSearch(filters).replace(/^\?/, ""))
      if (value === "") {
        next.delete(name)
      } else {
        next.set(name, value)
      }
      const search = next.toString()
      writeCookie(
        ALERT_FILTERS_COOKIE_NAME,
        encodeURIComponent(search),
        ALERT_FILTERS_COOKIE_MAX_AGE,
      )
      router.replace((search === "" ? pathname : `${pathname}?${search}`) as Route)
    },
    [filters, pathname, router],
  )
  const applyCustom = useCallback(
    (from: string, to: string) => {
      setCustom({ from, to })
      if (from === "" || to === "" || from > to) {
        setSeen("")
        apply("range", "")
        return
      }
      const value = serializeRange({ from, to })
      setSeen(value)
      apply("range", value)
    },
    [apply],
  )

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
        <Segmented
          current={typeof filters.range === "string" ? filters.range : ""}
          legend="when"
          onSelect={(value) => apply("range", value)}
          segments={RANGE_SEGMENTS}
        />
        <Segmented
          current={filters.severity ?? ""}
          legend="severity"
          onSelect={(value) => apply("severity", value)}
          segments={SEVERITY_SEGMENTS}
        />

        <Segmented
          current={filters.acknowledged === null ? "" : String(filters.acknowledged)}
          legend="state"
          onSelect={(value) => apply("acknowledged", value)}
          segments={STATE_SEGMENTS}
        />

        <div className="flex flex-col gap-2">
          <label className={GROUP_LABEL_CLASS} htmlFor="camera">
            camera
          </label>
          <select
            className={SELECT_CLASS}
            disabled={cameras.length === 0}
            id="camera"
            name="camera"
            onChange={(event) => apply("camera", event.target.value)}
            value={filters.camera ?? ""}
          >
            <option value="">
              {cameras.length === 0 ? "no cameras registered" : "all cameras"}
            </option>
            {cameras.map((camera) => (
              <option key={camera.id} value={camera.id}>
                {camera.hasEvents ? camera.id : `${camera.id} — no events`}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-2">
          <label className={GROUP_LABEL_CLASS} htmlFor="decision">
            decision
          </label>
          <select
            className={SELECT_CLASS}
            id="decision"
            name="decision"
            onChange={(event) => apply("decision", event.target.value)}
            value={filters.decision ?? ""}
          >
            <option value="">any decision</option>
            {DECISION_VALUES.map((value) => (
              <option key={value} value={value}>
                {DECISION_LABEL[value]}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-2">
          <label className={GROUP_LABEL_CLASS} htmlFor="sort">
            sort
          </label>
          <select
            className={SELECT_CLASS}
            id="sort"
            name="sort"
            onChange={(event) => apply("sort", event.target.value)}
            value={filters.sort ?? ""}
          >
            <option value="">order by received</option>
            {SORT_VALUES.map((value) => (
              <option key={value} value={value}>
                {SORT_LABEL[value]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="sr-only" htmlFor="range-from">
            from date
          </label>
          <input
            className={SELECT_CLASS}
            id="range-from"
            max={custom.to === "" ? civilToday() : custom.to}
            name="range-from"
            onChange={(event) => applyCustom(event.target.value, custom.to)}
            type="date"
            value={custom.from}
          />
          <span className="text-muted-foreground text-sm">to</span>
          <label className="sr-only" htmlFor="range-to">
            to date
          </label>
          <input
            className={SELECT_CLASS}
            id="range-to"
            max={civilToday()}
            min={custom.from === "" ? undefined : custom.from}
            name="range-to"
            onChange={(event) => applyCustom(custom.from, event.target.value)}
            type="date"
            value={custom.to}
          />
        </div>
        <div className="relative">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-2 left-2.5 size-3.5 text-muted-foreground"
          />
          <label className="sr-only" htmlFor="filter-loaded">
            filter loaded events
          </label>
          <input
            autoComplete="off"
            className="h-8 w-64 rounded-lg border border-border bg-background pr-2 pl-8 text-foreground text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            id="filter-loaded"
            name="filter-loaded"
            onChange={(event) => onTextChange(event.target.value)}
            placeholder="filter loaded events"
            type="search"
            value={text}
          />
        </div>
        {active > 0 || text !== "" ? (
          <Button onClick={onReset} size="xs" variant="ghost">
            {active === 1 ? "clear 1 filter" : `clear ${active} filters`}
          </Button>
        ) : null}
      </div>
    </div>
  )
}
