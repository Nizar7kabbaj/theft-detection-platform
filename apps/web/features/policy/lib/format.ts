import type { PolicyField } from "@/features/policy/schemas/policy"

export function formatUnit(value: number, unit: PolicyField["unit"]): string {
  if (unit === "percent") {
    return `${Math.round(value * 100)}%`
  }
  if (unit === "seconds") {
    return value >= 1 && Number.isInteger(value) ? `${value}s` : `${value.toFixed(1)}s`
  }
  return value.toFixed(2)
}

export function relativeTime(iso: string | null | undefined, now: number): string {
  if (iso === null || iso === undefined) {
    return "never"
  }
  const seconds = Math.round((now - Date.parse(iso)) / 1000)
  if (seconds < 60) {
    return "just now"
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}m ago`
  }
  if (seconds < 86400) {
    return `${Math.floor(seconds / 3600)}h ago`
  }
  return `${Math.floor(seconds / 86400)}d ago`
}

export function shortTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}
