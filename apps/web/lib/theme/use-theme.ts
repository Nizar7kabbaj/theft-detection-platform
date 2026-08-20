"use client"

import { useCallback, useState } from "react"
import { readCookie, writeCookie } from "@/lib/cookies/write"
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
  const raw = readCookie(THEME_COOKIE_NAME)
  return parseTheme(raw === null ? undefined : decodeURIComponent(raw))
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
    writeCookie(THEME_COOKIE_NAME, next, THEME_COOKIE_MAX_AGE)
    applyTheme(next)
    setThemeState(next)
  }, [])
  return { theme, setTheme }
}
