import type { DurationSpread } from "@/features/analytics/schemas/breakdown"

export type DurationBucket = {
  field: keyof DurationSpread
  label: string
  color: string
  dot: string
}

export const DURATION_BUCKETS: readonly DurationBucket[] = [
  { field: "under_60", label: "under 1m", color: "#0aa5f0", dot: "bg-[#0aa5f0]" },
  { field: "under_300", label: "1 to 5m", color: "#2f7bff", dot: "bg-[#2f7bff]" },
  { field: "under_900", label: "5 to 15m", color: "#6a5cff", dot: "bg-[#6a5cff]" },
  { field: "over_900", label: "over 15m", color: "#ff6a00", dot: "bg-[#ff6a00]" },
]

const MINUTE_SECONDS = 60
const HOUR_SECONDS = 3600
const DAY_SECONDS = 86400

function pair(major: number, majorUnit: string, minor: number, minorUnit: string): string {
  return minor === 0 ? `${major}${majorUnit}` : `${major}${majorUnit} ${minor}${minorUnit}`
}

export function formatDuration(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds))
  if (whole < MINUTE_SECONDS) {
    return `${whole}s`
  }
  if (whole < HOUR_SECONDS) {
    return `${Math.floor(whole / MINUTE_SECONDS)}m`
  }
  if (whole < DAY_SECONDS) {
    const hours = Math.floor(whole / HOUR_SECONDS)
    return pair(hours, "h", Math.floor((whole % HOUR_SECONDS) / MINUTE_SECONDS), "m")
  }
  const days = Math.floor(whole / DAY_SECONDS)
  return pair(days, "d", Math.floor((whole % DAY_SECONDS) / HOUR_SECONDS), "h")
}
