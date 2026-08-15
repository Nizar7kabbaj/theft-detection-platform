"use client"
import { useCallback, useState } from "react"
import {
  DEFAULT_THEME,
  parseTheme,
  THEME_COOKIE_MAX_AGE,
  THEME_COOKIE_NAME,
  type Theme,
} from "@/lib/theme/theme-cookie"

function readCookieTheme(): Theme {
  if (typeof document === "undefined") {
    return DEFAULT_THEME
  }
  const match = document.cookie.match(new RegExp(`(?:^|; )${THEME_COOKIE_NAME}=([^;]*)`))
  const raw = match?.[1]
  return parseTheme(raw === undefined ? undefined : decodeURIComponent(raw))
}

function applyTheme(theme: Theme): void {
  const dark =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
      : theme === "dark"
  document.documentElement.classList.toggle("dark", dark)
}

export function useTheme(): { theme: Theme; setTheme: (next: Theme) => void } {
  const [theme, setThemeState] = useState<Theme>(readCookieTheme)
  const setTheme = useCallback((next: Theme) => {
    document.cookie = `${THEME_COOKIE_NAME}=${next}; path=/; max-age=${THEME_COOKIE_MAX_AGE}; samesite=lax; secure`
    applyTheme(next)
    setThemeState(next)
  }, [])
  return { theme, setTheme }
}
