import type { Route } from "next"

const DEFAULT_PATH = "/dashboard"

export function safeReturnPath(raw: string | undefined | null): Route {
  if (raw === undefined || raw === null || raw === "") {
    return DEFAULT_PATH as Route
  }
  if (raw.length > 512) {
    return DEFAULT_PATH as Route
  }
  if (!raw.startsWith("/")) {
    return DEFAULT_PATH as Route
  }
  if (raw.startsWith("//") || raw.startsWith("/\\")) {
    return DEFAULT_PATH as Route
  }
  if (raw.startsWith("/login") || raw.startsWith("/auth/")) {
    return DEFAULT_PATH as Route
  }
  for (const char of raw) {
    const code = char.codePointAt(0) ?? 0
    if (code < 0x20 || code === 0x7f) {
      return DEFAULT_PATH as Route
    }
  }
  return raw as Route
}
