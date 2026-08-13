import "server-only"
import { cookies } from "next/headers"
import { experimental_taintUniqueValue as taintUniqueValue } from "react"

const ACCESS_COOKIE_NAME = "__Host-access_token"

export async function readAccessToken(): Promise<string | null> {
  const store = await cookies()
  const value = store.get(ACCESS_COOKIE_NAME)?.value
  if (value === undefined || value === "") {
    return null
  }
  taintUniqueValue("session token must not be passed to a client component", process, value)
  return value
}

export async function hasSession(): Promise<boolean> {
  return (await readAccessToken()) !== null
}
