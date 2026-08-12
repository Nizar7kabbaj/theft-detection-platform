import { CSRF_HEADER_NAME, readCsrfToken } from "@/lib/api/csrf"
import { ApiError, apiErrorFromResponse } from "@/lib/api/errors"

const REFRESH_PATH = "/auth/refresh"
const LOCK_NAME = "auth-refresh"

let inFlight: Promise<void> | null = null

async function callRefresh(): Promise<void> {
  const csrf = readCsrfToken()
  if (csrf === null) {
    throw new ApiError(401, "no csrf cookie", "session_invalid", null)
  }
  const response = await fetch(REFRESH_PATH, {
    method: "POST",
    credentials: "same-origin",
    headers: { [CSRF_HEADER_NAME]: csrf },
    cache: "no-store",
  })
  if (!response.ok) {
    throw await apiErrorFromResponse(response)
  }
}

async function refreshUnderLock(): Promise<void> {
  const before = readCsrfToken()
  if (typeof navigator === "undefined" || navigator.locks === undefined) {
    await callRefresh()
    return
  }
  await navigator.locks.request(LOCK_NAME, async () => {
    if (readCsrfToken() !== before) {
      return
    }
    await callRefresh()
  })
}

export function refreshSession(): Promise<void> {
  if (inFlight !== null) {
    return inFlight
  }
  const attempt = refreshUnderLock().finally(() => {
    inFlight = null
  })
  inFlight = attempt
  return attempt
}
