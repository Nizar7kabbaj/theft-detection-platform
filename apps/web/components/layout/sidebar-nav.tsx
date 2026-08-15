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

export function SidebarNav({
  sections,
  collapsed,
}: {
  sections: readonly NavSection[]
  collapsed: boolean
}) {
  const pathname = usePathname()
  return (
    <nav aria-label="main" className="flex flex-1 flex-col gap-4 overflow-y-auto px-2 py-3">
      {sections.map((section) => (
        <div key={section.heading} className="flex flex-col gap-1">
          <p
            className={cn(
              "px-2 text-muted-foreground text-xs uppercase tracking-wide",
              collapsed && "sr-only",
            )}
          >
            {section.heading}
          </p>
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
                  "flex items-center gap-3 rounded-md px-2 py-2 text-sm outline-none transition-colors",
                  "focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
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
