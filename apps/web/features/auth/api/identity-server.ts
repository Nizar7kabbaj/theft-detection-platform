import { cache } from "react"
import { type Identity, identityResponseSchema } from "@/features/auth/schemas/identity"
import { serverRead } from "@/lib/dal/request"
import "server-only"

export const fetchIdentity = cache(function fetchIdentity(): Promise<Identity> {
  return serverRead("/api/v1/me", { schema: identityResponseSchema })
})
