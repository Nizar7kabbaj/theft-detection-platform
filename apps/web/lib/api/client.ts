import "client-only"
import type { StandardSchemaV1 } from "@standard-schema/spec"
import { CSRF_HEADER_NAME, readCsrfToken } from "@/lib/api/csrf"
import {
  ApiError,
  apiErrorFromResponse,
  isRefreshable,
  NetworkError,
  ResponseShapeError,
} from "@/lib/api/errors"
import { refreshSession } from "@/lib/api/refresh"

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"])
const REQUEST_TIMEOUT_MS = 15_000
type RequestOptions<T> = {
  method?: string
  body?: unknown
  signal?: AbortSignal
  headers?: Record<string, string>
  schema?: StandardSchemaV1<unknown, T>
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
function deadline(caller: AbortSignal | undefined): AbortSignal {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS)
  return caller === undefined ? timeout : AbortSignal.any([caller, timeout])
}
async function readPayload<T>(
  response: Response,
  path: string,
  schema: StandardSchemaV1<unknown, T> | undefined,
): Promise<T> {
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T
  }
  const body: unknown = await response.json()
  if (schema === undefined) {
    return body as T
  }
  const result = await schema["~standard"].validate(body)
  if (result.issues !== undefined) {
    throw new ResponseShapeError(path, result.issues)
  }
  return result.value
}
export async function apiRequest<T>(path: string, options: RequestOptions<T> = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase()
  const serialized = options.body === undefined ? null : JSON.stringify(options.body)
  const extra = options.headers ?? {}
  const send = async (): Promise<Response> => {
    const init: RequestInit = {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers: buildHeaders(method, extra, serialized !== null),
      signal: deadline(options.signal),
    }
    if (serialized !== null) {
      init.body = serialized
    }
    try {
      return await fetch(path, init)
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") {
        throw cause
      }
      throw new NetworkError(cause)
    }
  }
  const first = await send()
  if (first.ok) {
    return readPayload<T>(first, path, options.schema)
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
    return readPayload<T>(retried, path, options.schema)
  }
  const retryError = await apiErrorFromResponse(retried)
  if (retryError.status === 401) {
    onSessionFailure?.(retryError)
  }
  throw retryError
}
