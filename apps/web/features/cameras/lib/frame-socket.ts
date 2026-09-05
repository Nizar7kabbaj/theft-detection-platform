import { backoffDelay, MAX_ATTEMPTS } from "@/lib/websocket/backoff"
import "client-only"

const WATCHDOG_MS = 20_000
const TERMINAL_REASONS = new Set([
  "session revoked",
  "insufficient permission",
  "unknown camera",
  "viewer limit reached",
])

export type FrameStatus = "connecting" | "open" | "waiting" | "stopped"
export type FrameHealth = "online" | "degraded" | "offline" | "unknown"

export type DetectionPerson = {
  track_id: number
  bbox: { x1: number; y1: number; x2: number; y2: number }
  keypoints: { x: number; y: number; confidence: number }[]
  score: number
  inference_state: string
}

export type DetectionObject = {
  track_id: number
  class_name: string
  bbox: { x1: number; y1: number; x2: number; y2: number }
  confidence: number
}
export type DetectionFrame = {
  frame_width: number
  frame_height: number
  detection_present: boolean
  persons: DetectionPerson[]
  objects?: DetectionObject[]
}

export type FrameHandlers = {
  onFrame: (blob: Blob) => void
  onHealth: (health: FrameHealth) => void
  onStatus: (status: FrameStatus) => void
  onDetection: (detection: DetectionFrame) => void
}

type StateEvent = {
  event: string
  data: { state: string; age_seconds: number | null }
}

const HEALTH_VALUES = new Set(["online", "degraded", "offline", "unknown"])

function readHealth(raw: string): FrameHealth | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  const envelope = parsed as Partial<StateEvent>
  if (envelope.event !== "state" || envelope.data === undefined) {
    return null
  }
  const state = envelope.data.state
  return HEALTH_VALUES.has(state) ? (state as FrameHealth) : null
}

export function openFrameSocket(cameraId: string, handlers: FrameHandlers): () => void {
  let socket: WebSocket | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let watchdog: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let closed = false

  const clearTimers = (): void => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
    if (watchdog !== null) {
      clearTimeout(watchdog)
      watchdog = null
    }
  }

  function readDetection(raw: string): DetectionFrame | null {
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      return null
    }
    const envelope = parsed as { event?: string; data?: DetectionFrame }
    if (envelope.event !== "detection" || envelope.data === undefined) {
      return null
    }
    return envelope.data
  }

  const drop = (): void => {
    clearTimers()
    const current = socket
    socket = null
    if (current === null) {
      return
    }
    current.onopen = null
    current.onmessage = null
    current.onerror = null
    current.onclose = null
    if (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING) {
      current.close(1000, "client closed")
    }
  }

  const schedule = (): void => {
    if (closed) {
      return
    }
    if (attempt >= MAX_ATTEMPTS) {
      handlers.onStatus("stopped")
      return
    }
    const delay = backoffDelay(attempt)
    attempt += 1
    handlers.onStatus("waiting")
    timer = setTimeout(() => {
      timer = null
      connect()
    }, delay)
  }

  const armWatchdog = (): void => {
    if (watchdog !== null) {
      clearTimeout(watchdog)
    }
    watchdog = setTimeout(() => {
      drop()
      schedule()
    }, WATCHDOG_MS)
  }

  const connect = (): void => {
    if (closed || socket !== null || typeof window === "undefined") {
      return
    }
    const url = `wss://${window.location.host}/ws/cameras/${encodeURIComponent(cameraId)}/frames`
    let next: WebSocket
    try {
      next = new WebSocket(url)
    } catch {
      schedule()
      return
    }
    next.binaryType = "blob"
    socket = next
    handlers.onStatus("connecting")

    next.onopen = () => {
      attempt = 0
      handlers.onStatus("open")
      armWatchdog()
    }

    next.onmessage = (event: MessageEvent<Blob | string>) => {
      armWatchdog()
      if (typeof event.data === "string") {
        const health = readHealth(event.data)
        if (health !== null) {
          handlers.onHealth(health)
          return
        }
        const detection = readDetection(event.data)
        if (detection !== null) {
          handlers.onDetection(detection)
        }
        return
      }
      handlers.onFrame(event.data)
    }

    next.onerror = () => {}

    next.onclose = (event: CloseEvent) => {
      socket = null
      clearTimers()
      if (closed || event.code === 1000) {
        return
      }
      if (event.code === 1008 && TERMINAL_REASONS.has(event.reason)) {
        handlers.onStatus("stopped")
        return
      }
      schedule()
    }
  }

  connect()

  return () => {
    closed = true
    drop()
  }
}
