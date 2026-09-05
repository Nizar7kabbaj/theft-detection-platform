import "server-only"
import { cache } from "react"
import {
  type RolePermissionMap,
  rolePermissionMapSchema,
  type UserCounts,
  type UserPage,
  userCountsSchema,
  userPageSchema,
} from "@/features/users/schemas/user"
import { authRead } from "@/lib/dal/auth-request"
import { serverRead } from "@/lib/dal/request"

export type UserQuery = {
  search?: string
  role?: string
  isActive?: boolean
  limit?: number
  offset?: number
}

function toQueryString(query: UserQuery): string {
  const params = new URLSearchParams()
  if (query.search !== undefined && query.search !== "") {
    params.set("search", query.search)
  }
  if (query.role !== undefined && query.role !== "") {
    params.set("role", query.role)
  }
  if (query.isActive !== undefined) {
    params.set("is_active", String(query.isActive))
  }
  if (query.limit !== undefined) {
    params.set("limit", String(query.limit))
  }
  if (query.offset !== undefined && query.offset > 0) {
    params.set("offset", String(query.offset))
  }
  const serialized = params.toString()
  return serialized === "" ? "" : `?${serialized}`
}

export function fetchUsers(query: UserQuery = {}): Promise<UserPage> {
  return authRead(`/auth/users${toQueryString(query)}`, { schema: userPageSchema })
}

export const fetchUserCounts = cache(function fetchUserCounts(): Promise<UserCounts> {
  return authRead("/auth/users/counts", { schema: userCountsSchema })
})

export const fetchRolePermissions = cache(
  function fetchRolePermissions(): Promise<RolePermissionMap> {
    return serverRead("/api/v1/permissions/roles", { schema: rolePermissionMapSchema })
  },
)
