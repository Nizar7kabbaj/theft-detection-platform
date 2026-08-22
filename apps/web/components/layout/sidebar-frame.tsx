"use client"
import type { ReactNode } from "react"
import { useCallback, useState } from "react"
import { Breadcrumb } from "@/components/layout/breadcrumb"
import { CommandPalette } from "@/components/layout/command-palette"
import { LogoWordmark } from "@/components/layout/logo-wordmark"
import { SidebarNav } from "@/components/layout/sidebar-nav"
import { SidebarSearch } from "@/components/layout/sidebar-search"
import { SidebarToggle } from "@/components/layout/sidebar-toggle"
import { SystemStatus } from "@/components/layout/system-status"
import { UserBlock } from "@/components/layout/user-block"
import { writeCookie } from "@/lib/cookies/write"
import { SIDEBAR_COOKIE_MAX_AGE, SIDEBAR_COOKIE_NAME } from "@/lib/layout/sidebar-cookie"
import type { NavSection } from "@/lib/navigation/links"
import { useCommandKey } from "@/lib/navigation/use-command-key"

const ASIDE_CLASS =
  "group/sidebar sticky top-0 flex h-dvh w-(--sidebar-width) shrink-0 flex-col overflow-hidden border-sidebar-border border-r bg-sidebar transition-[width] duration-200 ease-linear data-[collapsed=true]:w-(--sidebar-width-icon)"
const BRAND_CLASS =
  "flex h-20 shrink-0 items-center gap-3 overflow-hidden border-sidebar-border border-b px-3 pt-4 transition-[gap] duration-200 ease-linear group-data-[collapsed=true]/sidebar:justify-center group-data-[collapsed=true]/sidebar:gap-0 group-data-[collapsed=true]/sidebar:px-0"
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
  const [commandOpen, setCommandOpen] = useState(false)
  const onToggle = useCallback(() => {
    setCollapsed((current) => {
      const next = !current
      writeCookie(SIDEBAR_COOKIE_NAME, next ? "1" : "0", SIDEBAR_COOKIE_MAX_AGE)
      return next
    })
  }, [])
  const onCommandOpen = useCallback(() => setCommandOpen(true), [])
  useCommandKey(onCommandOpen)
  return (
    <div className="flex min-h-dvh bg-background">
      <CommandPalette sections={sections} open={commandOpen} onOpenChange={setCommandOpen} />
      <aside id="app-sidebar" data-collapsed={collapsed} className={ASIDE_CLASS}>
        <div className={BRAND_CLASS}>
          <LogoWordmark className="h-9 w-auto shrink-0 text-sidebar-foreground group-data-[collapsed=true]/sidebar:hidden" />
        </div>
        <SidebarSearch onOpen={onCommandOpen} />
        <SidebarNav sections={sections} />
        <UserBlock username={username} roles={roles} />
      </aside>
      <SidebarToggle collapsed={collapsed} onToggle={onToggle} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className={HEADER_CLASS}>
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
