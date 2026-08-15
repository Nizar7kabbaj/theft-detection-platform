"use client"
import { Menu } from "@base-ui/react/menu"
import { ChevronsUpDown, LogOut } from "lucide-react"
import { useCallback, useRef, useState } from "react"
import { ThemeMenuItems } from "@/components/layout/theme-menu-items"
import { CSRF_HEADER_NAME, readCsrfToken } from "@/lib/api/csrf"
import { cn } from "@/lib/utils"

const LOGOUT_PATH = "/auth/logout"
const LOGIN_PATH = "/login"

const TRIGGER_CLASS =
  "flex w-full items-center gap-2 overflow-hidden rounded-md px-2 py-2 text-left outline-none transition-[gap,padding,background-color] duration-200 ease-linear hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-sidebar-ring data-[popup-open]:bg-sidebar-accent group-data-[collapsed=true]/sidebar:justify-center group-data-[collapsed=true]/sidebar:gap-0 group-data-[collapsed=true]/sidebar:px-0"

const IDENTITY_CLASS =
  "flex min-w-0 max-w-40 flex-col transition-[max-width,opacity] duration-200 ease-linear group-data-[collapsed=true]/sidebar:max-w-0 group-data-[collapsed=true]/sidebar:opacity-0"

const POPUP_CLASS =
  "z-50 w-56 origin-[var(--transform-origin)] rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-lg outline-none"

const SIGN_OUT_CLASS =
  "flex w-full cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground"

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

export function UserBlock({ username, roles }: { username: string; roles: readonly string[] }) {
  const [pending, setPending] = useState(false)
  const inFlight = useRef(false)
  const role = roles.length === 0 ? "no role" : roles.join(", ")
  const onLogout = useCallback(async () => {
    if (inFlight.current) {
      return
    }
    inFlight.current = true
    setPending(true)
    const headers = new Headers({ Accept: "application/json" })
    const csrf = readCsrfToken()
    if (csrf !== null) {
      headers.set(CSRF_HEADER_NAME, csrf)
    }
    try {
      await fetch(LOGOUT_PATH, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers,
        keepalive: true,
      })
    } catch {
    } finally {
      window.location.assign(LOGIN_PATH)
    }
  }, [])
  return (
    <div className="border-sidebar-border border-t p-2">
      <Menu.Root>
        <Menu.Trigger className={TRIGGER_CLASS} aria-label={username}>
          <span
            aria-hidden="true"
            className="flex size-7 shrink-0 items-center justify-center rounded-full bg-sidebar-accent font-medium text-[0.7rem] text-sidebar-accent-foreground"
          >
            {initials(username)}
          </span>
          <span className={IDENTITY_CLASS}>
            <span className="truncate text-sidebar-foreground text-sm">{username}</span>
            <span className="truncate text-muted-foreground text-xs">{role}</span>
          </span>
          <ChevronsUpDown className="ml-auto size-4 shrink-0 text-muted-foreground transition-opacity duration-200 ease-linear group-data-[collapsed=true]/sidebar:hidden" />
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Positioner side="top" align="start" sideOffset={8}>
            <Menu.Popup className={POPUP_CLASS}>
              <div className="flex flex-col px-2 py-1.5">
                <span className="truncate font-medium text-sm">{username}</span>
                <span className="truncate text-muted-foreground text-xs">{role}</span>
              </div>
              <Menu.Separator className="-mx-1 my-1 h-px bg-border" />
              <ThemeMenuItems />
              <Menu.Separator className="-mx-1 my-1 h-px bg-border" />
              <Menu.Item
                onClick={onLogout}
                closeOnClick={false}
                disabled={pending}
                className={cn(SIGN_OUT_CLASS, "text-destructive")}
              >
                <LogOut className="size-4" />
                sign out
              </Menu.Item>
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
    </div>
  )
}
