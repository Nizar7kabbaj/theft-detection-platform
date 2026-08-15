export const THEME_COOKIE_NAME = "theme"
export const THEME_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
export const THEMES = ["light", "dark", "system"] as const
export type Theme = (typeof THEMES)[number]
export const DEFAULT_THEME: Theme = "dark"

export function parseTheme(value: string | undefined): Theme {
  for (const theme of THEMES) {
    if (theme === value) {
      return theme
    }
  }
  return DEFAULT_THEME
}
