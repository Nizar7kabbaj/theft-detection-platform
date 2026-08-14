import type { StandardSchemaV1 } from "@standard-schema/spec"

export const AUTH_CODE = {
  tokenExpired: "token_expired",
  sessionInvalid: "session_invalid",
  accountDisabled: "account_disabled",
} as const

const CSRF_DETAILS = new Set(["csrf token missing", "csrf token mismatch"])
const RETRYABLE_STATUS = new Set([429, 502, 503, 504])

type DetailShape = { message: string; code: string | null }

function parseDetail(body: unknown): DetailShape {
  if (typeof body !== "object" || body === null) {
    return { message: "", code: null }
  }
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === "string") {
    return { message: detail, code: null }
  }
  if (typeof detail === "object" && detail !== null) {
    const record = detail as Record<string, unknown>
    return {
      message: typeof record.message === "string" ? record.message : "",
      code: typeof record.code === "string" ? record.code : null,
    }
  }
  return { message: "", code: null }
}

function parseRetryAfter(response: Response): number | null {
  const raw = response.headers.get("retry-after")
  if (raw === null) {
    return null
  }
  const seconds = Number.parseInt(raw, 10)
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string | null
  readonly retryAfter: number | null
  constructor(status: number, message: string, code: string | null, retryAfter: number | null) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
    this.retryAfter = retryAfter
  }
}

export class ResponseShapeError extends Error {
  readonly path: string
  readonly issues: readonly StandardSchemaV1.Issue[]
  constructor(path: string, issues: readonly StandardSchemaV1.Issue[]) {
    super("response did not match the expected shape")
    this.name = "ResponseShapeError"
    this.path = path
    this.issues = issues
  }
}

export class NetworkError extends Error {
  constructor(cause: unknown) {
    super("the request did not reach the server", { cause })
    this.name = "NetworkError"
  }
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }
  const detail = parseDetail(body)
  const message = detail.message || response.statusText || "request failed"
  return new ApiError(response.status, message, detail.code, parseRetryAfter(response))
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export function isResponseShapeError(error: unknown): error is ResponseShapeError {
  return error instanceof ResponseShapeError
}

export function isNetworkError(error: unknown): error is NetworkError {
  return error instanceof NetworkError
}

export function isRefreshable(error: unknown): boolean {
  return isApiError(error) && error.status === 401 && error.code === AUTH_CODE.tokenExpired
}

export function needsLogin(error: unknown): boolean {
  if (!isApiError(error) || error.status !== 401) {
    return false
  }
  return error.code !== AUTH_CODE.tokenExpired
}

export function isCsrfFailure(error: unknown): boolean {
  return isApiError(error) && error.status === 403 && CSRF_DETAILS.has(error.message)
}

export function isPermissionDenied(error: unknown): boolean {
  return isApiError(error) && error.status === 403 && !CSRF_DETAILS.has(error.message)
}

export function isRetryable(error: unknown): boolean {
  if (isNetworkError(error)) {
    return true
  }
  if (isResponseShapeError(error)) {
    return false
  }
  if (!isApiError(error)) {
    return false
  }
  return RETRYABLE_STATUS.has(error.status)
}
