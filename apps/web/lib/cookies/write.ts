import "client-only"

export function writeCookie(name: string, value: string, maxAgeSeconds: number): void {
  document.cookie = `${name}=${value}; path=/; max-age=${maxAgeSeconds}; samesite=lax; secure`
}

export function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match?.[1] ?? null
}
