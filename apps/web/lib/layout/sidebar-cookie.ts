export const SIDEBAR_COOKIE_NAME = "sidebar_collapsed"
export const SIDEBAR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365

export function isCollapsedValue(value: string | undefined): boolean {
  return value === "1"
}
