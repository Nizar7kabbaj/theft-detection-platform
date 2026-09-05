const MINUTE = 60
const HOUR = 3600
const DAY = 86400
const WEEK = 604800

export function relativeTime(value: string | null | undefined, now: number): string {
  if (value === null || value === undefined) {
    return "never"
  }
  const then = Date.parse(value)
  if (Number.isNaN(then)) {
    return "never"
  }
  const seconds = Math.max(0, Math.floor((now - then) / 1000))
  if (seconds < MINUTE) {
    return "now"
  }
  if (seconds < HOUR) {
    return `${Math.floor(seconds / MINUTE)} min ago`
  }
  if (seconds < DAY) {
    return `${Math.floor(seconds / HOUR)} hr ago`
  }
  if (seconds < WEEK) {
    return `${Math.floor(seconds / DAY)} d ago`
  }
  return shortDate(value)
}

export function shortDate(value: string): string {
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) {
    return "unknown"
  }
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(parsed))
}

export function initials(username: string): string {
  const parts = username.split(/[-._]/).filter((part) => part.length > 0)
  const first = parts[0]?.[0] ?? username[0] ?? "?"
  const second = parts[1]?.[0] ?? parts[0]?.[1] ?? ""
  return `${first}${second}`.toUpperCase()
}
