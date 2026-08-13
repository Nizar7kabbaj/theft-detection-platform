import "server-only"
import type { StandardSchemaV1 } from "@standard-schema/spec"
import { ApiError, apiErrorFromResponse } from "@/lib/api/errors"
import { readAccessToken } from "@/lib/dal/session"

const ACCESS_COOKIE_NAME = "__Host-access_token"

type ServerReadOptions<T> = {
  signal?: AbortSignal
  schema?: StandardSchemaV1<unknown, T>
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

function apiBaseUrl(): string {
  const configured = process.env.API_BASE_URL
  if (configured === undefined || configured === "") {
    throw new Error("api base url is not configured")
  }
  return configured.replace(/\/+$/, "")
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

export async function serverRead<T>(path: string, options: ServerReadOptions<T> = {}): Promise<T> {
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
  }
  if (options.signal !== undefined) {
    init.signal = options.signal
  }
  const response = await fetch(`${apiBaseUrl()}${path}`, init)
  if (!response.ok) {
    throw await apiErrorFromResponse(response)
  }
  return readPayload<T>(response, path, options.schema)
}
