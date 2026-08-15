"use client"
import { Clock, LayoutDashboard, Settings, ShieldAlert, TrendingUp, Video } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import type { ComponentType } from "react"
import type { NavIcon, NavSection } from "@/lib/navigation/links"
import { cn } from "@/lib/utils"

const ICONS: Record<NavIcon, ComponentType<{ className?: string }>> = {
  dashboard: LayoutDashboard,
  alerts: ShieldAlert,
  cameras: Video,
  history: Clock,
  analytics: TrendingUp,
  settings: Settings,
}
const NAV_CLASS = "flex flex-1 flex-col gap-4 overflow-y-auto px-2 py-3"
const SECTION_CLASS = "flex flex-col gap-0.5"
const HEADING_CLASS = "px-2 pb-1 text-xs text-muted-foreground/80 uppercase tracking-wider"
const LINK_BASE_CLASS =
  "relative flex items-center gap-3 rounded-md px-2 py-1.5 font-medium text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-sidebar-ring"
const LINK_ACTIVE_CLASS =
  "bg-sidebar-accent text-sidebar-accent-foreground before:absolute before:top-1/2 before:left-0 before:h-4 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:bg-sidebar-primary"
const LINK_IDLE_CLASS =
  "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
export function SidebarNav({
  sections,
  collapsed,
}: {
  sections: readonly NavSection[]
  collapsed: boolean
}) {
  const pathname = usePathname()
  return (
    <nav aria-label="main" className={NAV_CLASS}>
      {sections.map((section) => (
        <div key={section.heading} className={SECTION_CLASS}>
          <p className={cn(HEADING_CLASS, collapsed && "sr-only")}>{section.heading}</p>
          {section.links.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`)
            const Icon = ICONS[link.icon]
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                title={collapsed ? link.label : undefined}
                className={cn(
                  LINK_BASE_CLASS,
                  active ? LINK_ACTIVE_CLASS : LINK_IDLE_CLASS,
                  collapsed && "justify-center px-0",
                )}
              >
                <Icon className="size-4 shrink-0" />
                <span className={cn(collapsed && "sr-only")}>{link.label}</span>
              </Link>
            )
          })}
        </div>
      ))}
    </nav>
  )
}
