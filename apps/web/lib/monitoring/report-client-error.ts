import "client-only"

const REPORT_PATH = "/client-error"

export function reportClientError(digest: string | undefined, path: string): void {
  const body = JSON.stringify({ digest, path })
  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    navigator.sendBeacon(REPORT_PATH, new Blob([body], { type: "application/json" }))
    return
  }
  void fetch(REPORT_PATH, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    keepalive: true,
  }).catch(() => undefined)
}
