"use client"
import { LogoutButton } from "@/components/layout/logout-button"
import { cn } from "@/lib/utils"

function initials(username: string): string {
  const parts = username.split(/[-_.\s]+/).filter((part) => part.length > 0)
  const first = parts[0]
  if (first === undefined) {
    return "?"
  }
  const second = parts[1]
  if (second === undefined) {
    return first.slice(0, 2).toUpperCase()
  }
  return `${first.slice(0, 1)}${second.slice(0, 1)}`.toUpperCase()
}

export function UserBlock({
  username,
  roles,
  collapsed,
}: {
  username: string
  roles: readonly string[]
  collapsed: boolean
}) {
  return (
    <div className="flex flex-col gap-2 border-sidebar-border border-t px-2 py-3">
      <div className={cn("flex items-center gap-2", collapsed && "justify-center")}>
        <span
          aria-hidden="true"
          className="flex size-7 shrink-0 items-center justify-center rounded-full bg-sidebar-accent font-medium text-[0.7rem] text-sidebar-accent-foreground"
        >
          {initials(username)}
        </span>
        <div className={cn("flex min-w-0 flex-col", collapsed && "sr-only")}>
          <span className="truncate text-sidebar-foreground text-sm">{username}</span>
          <span className="truncate text-muted-foreground text-xs">
            {roles.length === 0 ? "no role" : roles.join(", ")}
          </span>
        </div>
      </div>
      <LogoutButton collapsed={collapsed} />
    </div>
  )
}
