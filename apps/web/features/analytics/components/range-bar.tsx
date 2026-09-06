"use client"
import type { Route } from "next"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback } from "react"
import { UNIT_VALUES } from "@/features/analytics/api/bucket-unit"
import {
  type DateRange,
  PRESET_DAYS,
  presetRange,
  today,
} from "@/features/analytics/api/date-range"
import {
  decodeSelection,
  RANGE_COOKIE_MAX_AGE,
  RANGE_COOKIE_NAME,
} from "@/features/analytics/api/range-cookie"
import type { BucketUnit } from "@/features/analytics/schemas/timeseries"
import { writeCookie } from "@/lib/cookies/write"

const EYEBROW = "font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
const FIELD =
  "h-9 rounded-sm border border-border bg-card px-2.5 font-mono text-foreground text-xs outline-none transition-[border-color,box-shadow] duration-150 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40 [color-scheme:light_dark]"
const CHIP =
  "inline-flex h-7 items-center rounded-sm px-2.5 font-mono text-[11px] uppercase tracking-wide outline-none transition-[background-color,color] duration-150 focus-visible:ring-2 focus-visible:ring-ring/40"
const CHIP_ON = "bg-accent text-accent-foreground"
const CHIP_OFF = "text-muted-foreground hover:text-foreground"

export function RangeBar({ range, unit }: { range: DateRange; unit: BucketUnit }) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const currentDay = today()
  const isToday = range.start === currentDay && range.end === currentDay

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
      const selection = decodeSelection(
        [next.get("start") ?? "", next.get("end") ?? "", next.get("unit") ?? ""].join("|"),
      )
      writeCookie(
        RANGE_COOKIE_NAME,
        [selection.range.start ?? "", selection.range.end ?? "", selection.unit].join("|"),
        RANGE_COOKIE_MAX_AGE,
      )
      const query = next.toString()
      router.replace((query === "" ? pathname : `${pathname}?${query}`) as Route)
    },
    [pathname, router, searchParams],
  )

  return (
    <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label className={EYEBROW} htmlFor="range-start">
            from
          </label>
          <input
            autoComplete="off"
            className={FIELD}
            id="range-start"
            max={range.end ?? currentDay}
            name="start"
            onChange={(event) => write({ start: event.target.value })}
            type="date"
            value={range.start ?? ""}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className={EYEBROW} htmlFor="range-end">
            to
          </label>
          <input
            autoComplete="off"
            className={FIELD}
            id="range-end"
            max={currentDay}
            min={range.start ?? undefined}
            name="end"
            onChange={(event) => write({ end: event.target.value })}
            type="date"
            value={range.end ?? ""}
          />
        </div>
      </div>
      <div className="flex flex-col items-end gap-2">
        <fieldset className="flex items-center gap-1">
          <legend className="sr-only">preset range</legend>
          <button
            aria-pressed={isToday}
            className={`${CHIP} ${isToday ? CHIP_ON : CHIP_OFF}`}
            onClick={() => write({ start: currentDay, end: currentDay })}
            type="button"
          >
            today
          </button>
          {PRESET_DAYS.map((days) => (
            <button
              className={`${CHIP} ${CHIP_OFF}`}
              key={days}
              onClick={() => write(presetRange(days))}
              type="button"
            >
              {days}d
            </button>
          ))}
          <button
            className={`${CHIP} ${CHIP_OFF}`}
            onClick={() => write({ start: null, end: null })}
            type="button"
          >
            reset
          </button>
        </fieldset>
        <fieldset className="flex items-center gap-1">
          <legend className="sr-only">bucket size</legend>
          {UNIT_VALUES.map((value) => (
            <button
              aria-pressed={unit === value}
              className={`${CHIP} ${unit === value ? CHIP_ON : CHIP_OFF}`}
              key={value}
              onClick={() => write({ unit: value })}
              type="button"
            >
              {value}
            </button>
          ))}
        </fieldset>
      </div>
    </div>
  )
}
