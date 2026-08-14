import { type LoginInput, tokenResponseSchema } from "@/features/auth/schemas/login"
import { apiRequest } from "@/lib/api/client"
import { isApiError, isNetworkError } from "@/lib/api/errors"
import "client-only"

const LOGIN_PATH = "/auth/login"

export type LoginFailure =
  | { kind: "credentials" }
  | { kind: "locked"; retryAfter: number | null }
  | { kind: "unreachable" }
  | { kind: "rejected"; message: string }

export type LoginResult = { ok: true } | { ok: false; failure: LoginFailure }

export async function submitLogin(input: LoginInput): Promise<LoginResult> {
  try {
    await apiRequest(LOGIN_PATH, {
      method: "POST",
      body: input,
      schema: tokenResponseSchema,
    })
    return { ok: true }
  } catch (error) {
    return { ok: false, failure: classify(error) }
  }
}

function classify(error: unknown): LoginFailure {
  if (isNetworkError(error)) {
    return { kind: "unreachable" }
  }
  if (!isApiError(error)) {
    return { kind: "unreachable" }
  }
  if (error.status === 401) {
    return { kind: "credentials" }
  }
  if (error.status === 429) {
    return { kind: "locked", retryAfter: error.retryAfter }
  }
  if (error.status >= 500) {
    return { kind: "unreachable" }
  }
  return { kind: "rejected", message: error.message }
}
