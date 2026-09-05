import "server-only"
import type { StandardSchemaV1 } from "@standard-schema/spec"
import { ApiError, apiErrorFromResponse, NetworkError, ResponseShapeError } from "@/lib/api/errors"
import { readAccessToken } from "@/lib/dal/session"

const ACCESS_COOKIE_NAME = "__Host-access_token"
const SERVER_TIMEOUT_MS = 10_000

type AuthReadOptions<T> = {
  signal?: AbortSignal
  schema?: StandardSchemaV1<unknown, T>
}

function authBaseUrl(): string {
  const configured = process.env.AUTH_BASE_URL
  if (configured === undefined || configured === "") {
    throw new Error("auth base url is not configured")
  }
  return configured.replace(/\/+$/, "")
}

function deadline(caller: AbortSignal | undefined): AbortSignal {
  const timeout = AbortSignal.timeout(SERVER_TIMEOUT_MS)
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

export async function authRead<T>(path: string, options: AuthReadOptions<T> = {}): Promise<T> {
  const token = await readAccessToken()
  if (token === null) {
    throw new ApiError(401, "no session cookie", "session_invalid", null)
  }
  const headers = new Headers({
    Accept: "application/json",
    Cookie: `${ACCESS_COOKIE_NAME}=${token}`,
  })
  const init: RequestInit = {
    method: "GET",
    headers,
    cache: "no-store",
    redirect: "manual",
    signal: deadline(options.signal),
  }
  let response: Response
  try {
    response = await fetch(`${authBaseUrl()}${path}`, init)
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw cause
    }
    throw new NetworkError(cause)
  }
  if (!response.ok) {
    throw await apiErrorFromResponse(response)
  }
  return readPayload<T>(response, path, options.schema)
}
