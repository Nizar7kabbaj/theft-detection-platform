import "client-only"

const PROBE_PATH = "/healthz"
const PROBE_TIMEOUT_MS = 4_000
const RECHECK_MS = 15_000

export type Reachability = "online" | "offline" | "unknown"

type Listener = () => void

const listeners = new Set<Listener>()
let state: Reachability = "unknown"
let probing = false
let timer: ReturnType<typeof setTimeout> | null = null
let bound = false

function publish(next: Reachability): void {
  if (state === next) {
    return
  }
  state = next
  for (const listener of listeners) {
    listener()
  }
}

function clearRecheck(): void {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

function scheduleRecheck(): void {
  clearRecheck()
  timer = setTimeout(() => {
    timer = null
    void probe()
  }, RECHECK_MS)
}

export async function probe(): Promise<Reachability> {
  if (typeof window === "undefined") {
    return "unknown"
  }
  if (window.navigator.onLine === false) {
    clearRecheck()
    publish("offline")
    return "offline"
  }
  if (probing) {
    return state
  }
  probing = true
  const controller = new AbortController()
  const abort = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS)
  try {
    const response = await fetch(PROBE_PATH, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
      signal: controller.signal,
    })
    publish(response.ok ? "online" : "offline")
  } catch {
    publish("offline")
  } finally {
    clearTimeout(abort)
    probing = false
  }
  if (state === "offline") {
    scheduleRecheck()
  } else {
    clearRecheck()
  }
  return state
}

function handleOnline(): void {
  void probe()
}

function handleOffline(): void {
  clearRecheck()
  publish("offline")
}

function bindEvents(): void {
  if (bound || typeof window === "undefined") {
    return
  }
  bound = true
  window.addEventListener("online", handleOnline)
  window.addEventListener("offline", handleOffline)
  if (window.navigator.onLine === false) {
    publish("offline")
    return
  }
  publish("online")
}

export function subscribeReachability(listener: Listener): () => void {
  bindEvents()
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getReachability(): Reachability {
  return state
}

export function getServerReachability(): Reachability {
  return "unknown"
}

export function reportTransportFailure(): void {
  void probe()
}
