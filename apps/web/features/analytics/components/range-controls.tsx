"use client"

import type { Route } from "next"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback } from "react"
import { UNIT_VALUES } from "@/features/analytics/api/bucket-unit"
import {
  type DateRange,
  PRESET_DAYS,
  presetRange,
  todayUtc,
} from "@/features/analytics/api/date-range"
import {
  decodeSelection,
  RANGE_COOKIE_MAX_AGE,
  RANGE_COOKIE_NAME,
} from "@/features/analytics/api/range-cookie"
import type { BucketUnit } from "@/features/analytics/schemas/timeseries"
import { writeCookie } from "@/lib/cookies/write"

const FIELD_CLASS =
  "h-8 rounded-lg border border-border bg-background px-2 text-sm text-foreground outline-none transition-[border-color,box-shadow] duration-150 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 [color-scheme:light_dark]"
const LABEL_CLASS = "flex items-center gap-2 text-muted-foreground text-sm"
const GROUP_CLASS = "inline-flex items-center gap-1 rounded-xl bg-muted p-1"
const OPTION_CLASS =
  "inline-flex h-7 items-center rounded-lg px-2.5 text-sm outline-none transition-[background-color,color] duration-150 focus-visible:ring-3 focus-visible:ring-ring/50"
const ACTIVE_CLASS = "bg-background font-medium text-foreground shadow-xs"
const IDLE_CLASS = "text-muted-foreground hover:text-foreground"

function persist(search: URLSearchParams): void {
  const selection = decodeSelection(
    [search.get("start") ?? "", search.get("end") ?? "", search.get("unit") ?? ""].join("|"),
  )
  const value = [selection.range.start ?? "", selection.range.end ?? "", selection.unit].join("|")
  writeCookie(RANGE_COOKIE_NAME, value, RANGE_COOKIE_MAX_AGE)
}

export function RangeControls({ range, unit }: { range: DateRange; unit: BucketUnit }) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const today = todayUtc()
  const write = useCallback(
    (entries: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString())
      for (const [name, value] of Object.entries(entries)) {
        if (value === null || value === "") {
          next.delete(name)
        } else {
          next.set(name, value)
        }
      }
      persist(next)
      const query = next.toString()
      router.replace((query === "" ? pathname : `${pathname}?${query}`) as Route)
    },
    [pathname, router, searchParams],
  )
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
      <label className={LABEL_CLASS} htmlFor="start">
        from
        <input
          className={FIELD_CLASS}
          id="start"
          max={range.end ?? today}
          name="start"
          onChange={(event) => write({ start: event.target.value })}
          type="date"
          value={range.start ?? ""}
        />
      </label>
      <label className={LABEL_CLASS} htmlFor="end">
        to
        <input
          className={FIELD_CLASS}
          id="end"
          max={today}
          min={range.start ?? undefined}
          name="end"
          onChange={(event) => write({ end: event.target.value })}
          type="date"
          value={range.end ?? ""}
        />
      </label>
      <div className={GROUP_CLASS}>
        {PRESET_DAYS.map((days) => (
          <button
            className={`${OPTION_CLASS} ${IDLE_CLASS}`}
            key={days}
            onClick={() => write(presetRange(days))}
            type="button"
          >
            {days}d
          </button>
        ))}
        <button
          className={`${OPTION_CLASS} ${IDLE_CLASS}`}
          onClick={() => write({ start: null, end: null })}
          type="button"
        >
          reset
        </button>
      </div>
      <fieldset className="flex items-center gap-2">
        <legend className="sr-only">bucket size</legend>
        <span aria-hidden="true" className="text-muted-foreground text-sm">
          bucket
        </span>
        <div className={GROUP_CLASS}>
          {UNIT_VALUES.map((value) => (
            <button
              aria-pressed={unit === value}
              className={`${OPTION_CLASS} ${unit === value ? ACTIVE_CLASS : IDLE_CLASS}`}
              key={value}
              onClick={() => write({ unit: value })}
              type="button"
            >
              {value}
            </button>
          ))}
        </div>
      </fieldset>
    </div>
  )
}
