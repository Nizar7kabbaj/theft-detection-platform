import * as z from "zod/mini"

export const ROLE_VALUES = [
  "admin",
  "operator",
  "viewer",
  "ml_engineer",
  "compliance",
  "detector",
] as const

export const roleSchema = z.enum(ROLE_VALUES)
export type Role = z.output<typeof roleSchema>

export const ROLE_LABELS = new Map<Role, string>([
  ["admin", "admin"],
  ["operator", "operator"],
  ["viewer", "viewer"],
  ["ml_engineer", "ml engineer"],
  ["compliance", "compliance"],
  ["detector", "detector"],
])

export const userSummarySchema = z.object({
  id: z.string().check(z.minLength(1), z.maxLength(64)),
  username: z.string().check(z.minLength(1), z.maxLength(50)),
  roles: z.array(z.string().check(z.maxLength(32))),
  is_active: z.boolean(),
  created_at: z.iso.datetime({ offset: true }),
  last_active_at: z.nullish(z.iso.datetime({ offset: true })),
})

export type UserSummary = z.output<typeof userSummarySchema>

export const userPageSchema = z.object({
  items: z.array(userSummarySchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
})

export type UserPage = z.output<typeof userPageSchema>

export const userCountsSchema = z.object({
  total: z.number(),
  active: z.number(),
  disabled: z.number(),
  live_sessions: z.number(),
})

export type UserCounts = z.output<typeof userCountsSchema>

export const revokeSessionsSchema = z.object({
  revoked: z.number(),
})

export const eraseAccountSchema = z.object({
  records_erased: z.number(),
  completed: z.boolean(),
})

export type EraseAccount = z.output<typeof eraseAccountSchema>
export type RevokeSessions = z.output<typeof revokeSessionsSchema>

export const MIN_PASSWORD_LENGTH = 12

export function knownRoles(roles: readonly string[]): Role[] {
  return roles.filter((role): role is Role => ROLE_LABELS.has(role as Role))
}

export const rolePermissionMapSchema = z.object({
  permissions: z.array(z.string().check(z.maxLength(64))),
  roles: z.record(z.string(), z.array(z.string().check(z.maxLength(64)))),
})

export type RolePermissionMap = z.output<typeof rolePermissionMapSchema>

export function grantedFor(map: RolePermissionMap, roles: readonly string[]): ReadonlySet<string> {
  const granted = new Set<string>()
  for (const role of roles) {
    for (const permission of map.roles[role] ?? []) {
      granted.add(permission)
    }
  }
  return granted
}
