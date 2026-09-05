import {
  type EraseAccount,
  eraseAccountSchema,
  type RevokeSessions,
  revokeSessionsSchema,
  type UserSummary,
  userSummarySchema,
} from "@/features/users/schemas/user"
import { apiRequest } from "@/lib/api/client"
import "client-only"

export type CreateUserInput = {
  username: string
  password: string
  roles: string[]
}

export function createUser(input: CreateUserInput): Promise<UserSummary> {
  return apiRequest("/auth/users", {
    method: "POST",
    body: input,
    schema: userSummarySchema,
  })
}

export function updateRoles(userId: string, roles: string[]): Promise<UserSummary> {
  return apiRequest(`/auth/users/${userId}/roles`, {
    method: "PUT",
    body: { roles },
    schema: userSummarySchema,
  })
}

export function setUserActive(userId: string, isActive: boolean): Promise<UserSummary> {
  return apiRequest(`/auth/users/${userId}/active`, {
    method: "PUT",
    body: { is_active: isActive },
    schema: userSummarySchema,
  })
}

export function resetPassword(userId: string, password: string): Promise<void> {
  return apiRequest(`/auth/users/${userId}/password`, {
    method: "PUT",
    body: { password },
  })
}

export function revokeUserSessions(userId: string): Promise<RevokeSessions> {
  return apiRequest(`/auth/users/${userId}/sessions/revoke`, {
    method: "POST",
    schema: revokeSessionsSchema,
  })
}

export function deleteUser(userId: string): Promise<EraseAccount> {
  return apiRequest(`/auth/users/${userId}`, {
    method: "DELETE",
    schema: eraseAccountSchema,
  })
}
