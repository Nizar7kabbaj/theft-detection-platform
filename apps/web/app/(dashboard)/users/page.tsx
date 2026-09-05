import type { Metadata } from "next"
import { cookies } from "next/headers"
import { redirect } from "next/navigation"
import { PageHeader } from "@/components/layout/page-header"
import { AbsentPanel } from "@/features/alerts/components/absent-panel"
import { fetchIdentity } from "@/features/auth/api/identity-server"
import type { Identity } from "@/features/auth/schemas/identity"
import { parseStoredFilters, USER_FILTERS_COOKIE_NAME } from "@/features/users/api/user-cookie"
import {
  fetchRolePermissions,
  fetchUserCounts,
  fetchUsers,
  type UserQuery,
} from "@/features/users/api/users-server"
import { UserConsole } from "@/features/users/components/user-console"
import { UserTiles } from "@/features/users/components/user-tiles"
import { isApiError } from "@/lib/api/errors"

export const metadata: Metadata = { title: "users" }
export const dynamic = "force-dynamic"

const DESCRIPTION = "accounts, roles and access to the platform"
const PAGE_SIZE = 50

function activeFlag(status: string): boolean | undefined {
  if (status === "active") {
    return true
  }
  if (status === "disabled") {
    return false
  }
  return undefined
}

export default async function UsersPage() {
  let identity: Identity
  try {
    identity = await fetchIdentity()
  } catch (error) {
    if (isApiError(error) && error.status === 401) {
      redirect("/login?reason=session_ended")
    }
    throw error
  }
  const permissions = new Set(identity.permissions)

  if (!permissions.has("user:read")) {
    return (
      <section className="flex flex-1 flex-col gap-5">
        <PageHeader title="users" description={DESCRIPTION} />
        <AbsentPanel title="user management" reason="managing accounts requires the admin role" />
      </section>
    )
  }

  const jar = await cookies()
  const filters = parseStoredFilters(jar.get(USER_FILTERS_COOKIE_NAME)?.value)

  const active = activeFlag(filters.status)
  const query: UserQuery = {
    search: filters.search,
    role: filters.role,
    limit: PAGE_SIZE,
    offset: filters.page * PAGE_SIZE,
    ...(active === undefined ? {} : { isActive: active }),
  }

  const [counts, page, permissionMap] = await Promise.all([
    fetchUserCounts(),
    fetchUsers(query),
    fetchRolePermissions(),
  ])

  return (
    <section className="flex flex-1 flex-col gap-5">
      <PageHeader title="users" description={DESCRIPTION} />
      <UserTiles counts={counts} />
      <UserConsole
        initialUsers={page.items}
        total={page.total}
        pageSize={PAGE_SIZE}
        permissionMap={permissionMap}
        renderedAt={Date.now()}
        canWrite={permissions.has("user:write")}
        currentUserId={identity.user_id}
        initialFilters={filters}
      />
    </section>
  )
}
