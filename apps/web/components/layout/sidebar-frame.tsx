"use client"

import { ScanEye } from "lucide-react"
import type { ReactNode } from "react"
import { useCallback, useState } from "react"
import { Breadcrumb } from "@/components/layout/breadcrumb"
import { SidebarNav } from "@/components/layout/sidebar-nav"
import { SidebarToggle } from "@/components/layout/sidebar-toggle"
import { SystemStatus } from "@/components/layout/system-status"
import { UserBlock } from "@/components/layout/user-block"
import { SIDEBAR_COOKIE_MAX_AGE, SIDEBAR_COOKIE_NAME } from "@/lib/layout/sidebar-cookie"
import type { NavSection } from "@/lib/navigation/links"
import { cn } from "@/lib/utils"

const ASIDE_CLASS =
  "sticky top-0 flex h-dvh shrink-0 flex-col border-sidebar-border border-r bg-sidebar transition-[width] duration-150"

const BRAND_CLASS = "flex h-12 shrink-0 items-center gap-2 px-3"

const HEADER_CLASS =
  "sticky top-0 z-10 flex h-12 shrink-0 items-center gap-2.5 border-border border-b bg-background/95 px-3 backdrop-blur"

export function SidebarFrame({
  sections,
  username,
  roles,
  initialCollapsed,
  children,
}: {
  sections: readonly NavSection[]
  username: string
  roles: readonly string[]
  initialCollapsed: boolean
  children: ReactNode
}) {
  const [collapsed, setCollapsed] = useState(initialCollapsed)

  const onToggle = useCallback(() => {
    setCollapsed((current) => {
      const next = !current
      document.cookie = `${SIDEBAR_COOKIE_NAME}=${next ? "1" : "0"}; path=/; max-age=${SIDEBAR_COOKIE_MAX_AGE}; samesite=lax; secure`
      return next
    })
  }, [])

  return (
    <div className="flex min-h-dvh bg-background">
      <aside id="app-sidebar" className={cn(ASIDE_CLASS, collapsed ? "w-14" : "w-60")}>
        <div className={cn(BRAND_CLASS, collapsed && "justify-center px-0")}>
          <ScanEye className="size-5 shrink-0 text-sidebar-primary" />
          <span
            className={cn(
              "truncate font-medium text-sidebar-foreground text-[0.8125rem]/5",
              collapsed && "sr-only",
            )}
          >
            Dashboard
          </span>
        </div>
        <SidebarNav sections={sections} collapsed={collapsed} />
        <UserBlock username={username} roles={roles} collapsed={collapsed} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className={HEADER_CLASS}>
          <SidebarToggle collapsed={collapsed} onToggle={onToggle} />
          <Breadcrumb />
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <SystemStatus />
          </div>
        </header>
        {children}
      </div>
    </div>
  )
}
