import type { Route } from "next"
import { PERMISSION, type Permission } from "@/features/auth/schemas/identity"
export type NavIcon = "dashboard" | "alerts" | "cameras" | "history" | "analytics" | "settings"
export type NavLink = {
  href: Route
  label: string
  icon: NavIcon
  permission: Permission
}
export type NavSection = {
  heading: string
  links: readonly NavLink[]
}
export const NAV_SECTIONS: readonly NavSection[] = [
  {
    heading: "monitoring",
    links: [
      {
        href: "/dashboard",
        label: "dashboard",
        icon: "dashboard",
        permission: PERMISSION.statsRead,
      },
      {
        href: "/alerts",
        label: "alerts",
        icon: "alerts",
        permission: PERMISSION.alertRead,
      },
      {
        href: "/cameras",
        label: "cameras",
        icon: "cameras",
        permission: PERMISSION.cameraRead,
      },
    ],
  },
  {
    heading: "review",
    links: [
      {
        href: "/history",
        label: "history",
        icon: "history",
        permission: PERMISSION.alertRead,
      },
      {
        href: "/analytics",
        label: "analytics",
        icon: "analytics",
        permission: PERMISSION.statsRead,
      },
    ],
  },
  {
    heading: "manage",
    links: [
      {
        href: "/settings",
        label: "settings",
        icon: "settings",
        permission: PERMISSION.cameraWrite,
      },
    ],
  },
]
export function visibleSections(permissions: readonly string[]): NavSection[] {
  const granted = new Set(permissions)
  const sections: NavSection[] = []
  for (const section of NAV_SECTIONS) {
    const links = section.links.filter((link) => granted.has(link.permission))
    if (links.length > 0) {
      sections.push({ heading: section.heading, links })
    }
  }
  return sections
}
