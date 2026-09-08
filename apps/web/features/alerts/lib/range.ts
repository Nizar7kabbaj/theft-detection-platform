import { STORE_TIME_ZONE } from "@/lib/time/zone"

export const RANGE_PRESETS = ["today", "7d", "30d", "90d"] as const

export type RangePreset = (typeof RANGE_PRESETS)[number]
export type CustomRange = { from: string; to: string }
export type AlertRange = RangePreset | CustomRange

const DAY_MS = 86_400_000
const CIVIL_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const PRESET_DAYS: Record<RangePreset, number> = {
  today: 1,
  "7d": 7,
  "30d": 30,
  "90d": 90,
}

const ZONE_PARTS = new Intl.DateTimeFormat("en-CA", {
  timeZone: STORE_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
})

function readParts(instant: Date): Record<string, number> {
  const parts = ZONE_PARTS.formatToParts(instant)
  const out: Record<string, number> = {}
  for (const part of parts) {
    if (part.type !== "literal") {
      out[part.type] = Number(part.value)
    }
  }
  return out
}

function zoneOffsetMs(instant: number): number {
  const parts = readParts(new Date(instant))
  const hour = (parts.hour ?? 0) % 24
  const asUtc = Date.UTC(
    parts.year ?? 1970,
    (parts.month ?? 1) - 1,
    parts.day ?? 1,
    hour,
    parts.minute ?? 0,
    parts.second ?? 0,
  )
  return asUtc - instant
}

function civilParts(civil: string): [number, number, number] {
  const chunks = civil.split("-")
  return [Number(chunks[0]), Number(chunks[1]), Number(chunks[2])]
}

function isRealCivil(civil: string): boolean {
  if (!CIVIL_PATTERN.test(civil)) {
    return false
  }
  const [year, month, day] = civilParts(civil)
  const probe = new Date(Date.UTC(year, month - 1, day))
  return (
    probe.getUTCFullYear() === year &&
    probe.getUTCMonth() === month - 1 &&
    probe.getUTCDate() === day
  )
}

function resolveBoundary(naive: number): number {
  const guess = naive - zoneOffsetMs(naive)
  return naive - zoneOffsetMs(guess)
}

function startOfCivilDay(civil: string): number {
  const [year, month, day] = civilParts(civil)
  return resolveBoundary(Date.UTC(year, month - 1, day))
}

function endOfCivilDay(civil: string): number {
  const [year, month, day] = civilParts(civil)
  return resolveBoundary(Date.UTC(year, month - 1, day) + DAY_MS) - 1
}

function shiftCivil(civil: string, days: number): string {
  const [year, month, day] = civilParts(civil)
  const shifted = new Date(Date.UTC(year, month - 1, day + days))
  const paddedMonth = String(shifted.getUTCMonth() + 1).padStart(2, "0")
  const paddedDay = String(shifted.getUTCDate()).padStart(2, "0")
  return `${shifted.getUTCFullYear()}-${paddedMonth}-${paddedDay}`
}

export function civilToday(now: Date = new Date()): string {
  const parts = readParts(now)
  const paddedMonth = String(parts.month ?? 1).padStart(2, "0")
  const paddedDay = String(parts.day ?? 1).padStart(2, "0")
  return `${parts.year ?? 1970}-${paddedMonth}-${paddedDay}`
}

export function isRangePreset(value: string): value is RangePreset {
  return (RANGE_PRESETS as readonly string[]).includes(value)
}

export function parseRange(value: string | null | undefined): AlertRange | null {
  if (value === null || value === undefined || value === "") {
    return null
  }
  if (isRangePreset(value)) {
    return value
  }
  const chunks = value.split("..")
  if (chunks.length !== 2) {
    return null
  }
  const from = chunks[0] ?? ""
  const to = chunks[1] ?? ""
  if (!isRealCivil(from) || !isRealCivil(to) || from > to) {
    return null
  }
  return { from, to }
}

export function serializeRange(range: AlertRange): string {
  return typeof range === "string" ? range : `${range.from}..${range.to}`
}

export function rangeBounds(
  range: AlertRange,
  now: Date = new Date(),
): { start: string; end: string } {
  if (typeof range === "string") {
    const today = civilToday(now)
    const first = shiftCivil(today, 1 - PRESET_DAYS[range])
    return {
      start: new Date(startOfCivilDay(first)).toISOString(),
      end: new Date(endOfCivilDay(today)).toISOString(),
    }
  }
  return {
    start: new Date(startOfCivilDay(range.from)).toISOString(),
    end: new Date(endOfCivilDay(range.to)).toISOString(),
  }
}
