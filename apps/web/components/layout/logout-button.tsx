"use client"
import { LogOut } from "lucide-react"
import { useCallback, useState } from "react"
import { Button } from "@/components/ui/button"
import { CSRF_HEADER_NAME, readCsrfToken } from "@/lib/api/csrf"
import { cn } from "@/lib/utils"

const LOGOUT_PATH = "/auth/logout"
const LOGIN_PATH = "/login"

export function LogoutButton({ collapsed }: { collapsed: boolean }) {
  const [pending, setPending] = useState(false)
  const onLogout = useCallback(async () => {
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
    <Button
      type="button"
      variant="ghost"
      size={collapsed ? "icon-sm" : "sm"}
      onClick={onLogout}
      disabled={pending}
      aria-label="sign out"
      title={collapsed ? "sign out" : undefined}
      className={cn(!collapsed && "w-full justify-start gap-2")}
    >
      <LogOut />
      <span className={cn(collapsed && "sr-only")}>sign out</span>
    </Button>
  )
}
