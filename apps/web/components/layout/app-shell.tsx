import type { ReactNode } from "react"
import { ConnectionBanner } from "@/components/layout/connection-banner"
import { SidebarFrame } from "@/components/layout/sidebar-frame"
import type { Identity } from "@/features/auth/schemas/identity"
import { visibleSections } from "@/lib/navigation/links"

const SKIP_LINK_CLASS =
  "sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:border focus:border-border focus:bg-background focus:px-3 focus:py-2 focus:text-sm"

export function AppShell({
  identity,
  collapsed,
  children,
}: {
  identity: Identity
  collapsed: boolean
  children: ReactNode
}) {
  return (
    <>
      <a href="#main-content" className={SKIP_LINK_CLASS}>
        skip to content
      </a>
      <SidebarFrame
        sections={visibleSections(identity.permissions)}
        username={identity.username}
        roles={identity.roles}
        initialCollapsed={collapsed}
      >
        <main
          id="main-content"
          tabIndex={-1}
          className="flex min-w-0 flex-1 flex-col gap-6 p-6 outline-none"
        >
          <ConnectionBanner />
          {children}
        </main>
      </SidebarFrame>
    </>
  )
}
