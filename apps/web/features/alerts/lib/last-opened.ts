import "client-only"

const KEY = "alerts:last-opened"

export function rememberOpened(id: string): void {
  try {
    window.sessionStorage.setItem(KEY, id)
  } catch {
    return
  }
}

export function readOpened(): string | null {
  try {
    return window.sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}
