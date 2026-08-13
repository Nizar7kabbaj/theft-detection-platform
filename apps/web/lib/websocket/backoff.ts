import "client-only"

const BASE_DELAY_MS = 500
const MAX_DELAY_MS = 30_000
const MIN_DELAY_MS = 1_000
const GLOBAL_SPACING_MS = 2_000

export const MAX_ATTEMPTS = 12

let lastScheduledAt = 0

export function backoffDelay(attempt: number, random: () => number = Math.random): number {
  const exponential = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt)
  return Math.max(MIN_DELAY_MS, Math.round(random() * exponential))
}

export function reserveConnectSlot(delayMs: number, now: number = Date.now()): number {
  const earliest = Math.max(now + delayMs, lastScheduledAt + GLOBAL_SPACING_MS)
  lastScheduledAt = earliest
  return earliest - now
}

export function resetConnectSpacing(): void {
  lastScheduledAt = 0
}
