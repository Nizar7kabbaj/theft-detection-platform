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
const HEADING_CLASS =
  "h-5 overflow-hidden truncate px-2 text-xs text-muted-foreground/80 uppercase tracking-wider transition-[height,opacity,margin] duration-200 ease-linear group-data-[collapsed=true]/sidebar:-mb-1 group-data-[collapsed=true]/sidebar:h-0 group-data-[collapsed=true]/sidebar:opacity-0"
const LINK_BASE_CLASS =
  "relative flex items-center gap-3 overflow-hidden rounded-md px-2 py-1.5 font-medium text-sm outline-none transition-[gap,padding,background-color,color] duration-200 ease-linear focus-visible:ring-2 focus-visible:ring-sidebar-ring group-data-[collapsed=true]/sidebar:justify-center group-data-[collapsed=true]/sidebar:gap-0 group-data-[collapsed=true]/sidebar:px-0"
const LINK_ACTIVE_CLASS =
  "bg-sidebar-accent text-sidebar-accent-foreground before:absolute before:top-1/2 before:left-0 before:h-4 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:bg-sidebar-primary"
const LINK_IDLE_CLASS =
  "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
const LABEL_CLASS =
  "max-w-40 truncate transition-[max-width,opacity] duration-200 ease-linear group-data-[collapsed=true]/sidebar:max-w-0 group-data-[collapsed=true]/sidebar:opacity-0"
export function SidebarNav({ sections }: { sections: readonly NavSection[] }) {
  const pathname = usePathname()
  return (
    <nav aria-label="main" className={NAV_CLASS}>
      {sections.map((section) => (
        <div key={section.heading} className={SECTION_CLASS}>
          <p className={HEADING_CLASS}>{section.heading}</p>
          {section.links.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`)
            const Icon = ICONS[link.icon]
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={cn(LINK_BASE_CLASS, active ? LINK_ACTIVE_CLASS : LINK_IDLE_CLASS)}
              >
                <Icon className="size-4 shrink-0" />
                <span className={LABEL_CLASS}>{link.label}</span>
              </Link>
            )
          })}
        </div>
      ))}
    </nav>
  )
}
