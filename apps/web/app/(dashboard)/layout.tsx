import type { Route } from "next"
import { cookies, headers } from "next/headers"
import { redirect } from "next/navigation"
import type { ReactNode } from "react"
import { AppShell } from "@/components/layout/app-shell"
import { fetchIdentity } from "@/features/auth/api/identity-server"
import type { Identity } from "@/features/auth/schemas/identity"
import { isApiError } from "@/lib/api/errors"
import { isCollapsedValue, SIDEBAR_COOKIE_NAME } from "@/lib/layout/sidebar-cookie"
import { QueryProvider } from "@/providers/query-provider"

const LOGIN_PATH = "/login"

export default async function DashboardLayout({ children }: Readonly<{ children: ReactNode }>) {
  const [store, headerList] = await Promise.all([cookies(), headers()])
  const collapsed = isCollapsedValue(store.get(SIDEBAR_COOKIE_NAME)?.value)
  let identity: Identity
  try {
    identity = await fetchIdentity()
  } catch (error) {
    if (isApiError(error) && error.status === 401) {
      const from = headerList.get("x-pathname")
      const target =
        from === null || from === "" || from === "/dashboard"
          ? LOGIN_PATH
          : `${LOGIN_PATH}?from=${encodeURIComponent(from)}`
      redirect(target as Route)
    }
    throw error
  }
  return (
    <QueryProvider>
      <AppShell identity={identity} collapsed={collapsed}>
        {children}
      </AppShell>
    </QueryProvider>
  )
}
