import { CSRF_HEADER_NAME, readCsrfToken } from "@/lib/api/csrf"
import { ApiError, apiErrorFromResponse, isRefreshable } from "@/lib/api/errors"
import { refreshSession } from "@/lib/api/refresh"

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"])

type RequestOptions = {
  method?: string
  body?: unknown
  signal?: AbortSignal
  headers?: Record<string, string>
}

type SessionFailureHandler = (error: ApiError) => void

let onSessionFailure: SessionFailureHandler | null = null

export function setSessionFailureHandler(handler: SessionFailureHandler | null): void {
  onSessionFailure = handler
}

function buildHeaders(method: string, extra: Record<string, string>, hasBody: boolean): Headers {
  const headers = new Headers(extra)
  headers.set("Accept", "application/json")
  if (hasBody) {
    headers.set("Content-Type", "application/json")
  }
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCsrfToken()
    if (csrf !== null) {
      headers.set(CSRF_HEADER_NAME, csrf)
    }
  }
  return headers
}

async function readPayload<T>(response: Response): Promise<T> {
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T
  }
  return (await response.json()) as T
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase()
  const serialized = options.body === undefined ? null : JSON.stringify(options.body)
  const extra = options.headers ?? {}

  const send = (): Promise<Response> => {
    const init: RequestInit = {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers: buildHeaders(method, extra, serialized !== null),
    }
    if (serialized !== null) {
      init.body = serialized
    }
    if (options.signal !== undefined) {
      init.signal = options.signal
    }
    return fetch(path, init)
  }

  const first = await send()
  if (first.ok) {
    return readPayload<T>(first)
  }

  const error = await apiErrorFromResponse(first)
  if (!isRefreshable(error)) {
    throw error
  }

  try {
    await refreshSession()
  } catch (refreshError) {
    if (refreshError instanceof ApiError) {
      onSessionFailure?.(refreshError)
    }
    throw refreshError
  }

  const retried = await send()
  if (retried.ok) {
    return readPayload<T>(retried)
  }

  const retryError = await apiErrorFromResponse(retried)
  if (retryError.status === 401) {
    onSessionFailure?.(retryError)
  }
  throw retryError
}
