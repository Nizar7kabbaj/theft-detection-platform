const CSRF_COOKIE_NAME = "__Host-csrf"
export const CSRF_HEADER_NAME = "X-CSRF-Token"

export function readCsrfToken(): string | null {
  if (typeof document === "undefined") {
    return null
  }
  for (const entry of document.cookie.split(";")) {
    const separator = entry.indexOf("=")
    if (separator === -1) {
      continue
    }
    if (entry.slice(0, separator).trim() !== CSRF_COOKIE_NAME) {
      continue
    }
    const value = entry.slice(separator + 1).trim()
    return value === "" ? null : decodeURIComponent(value)
  }
  return null
}
