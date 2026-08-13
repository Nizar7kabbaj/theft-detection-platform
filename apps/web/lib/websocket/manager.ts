import { apiRequest } from "@/lib/api/client"
import { needsLogin } from "@/lib/api/errors"
import {
  backoffDelay,
  MAX_ATTEMPTS,
  reserveConnectSlot,
  resetConnectSpacing,
} from "@/lib/websocket/backoff"
import { isPing, parseEnvelope, type StreamEnvelope } from "@/lib/websocket/envelope"
import "client-only"

const WATCHDOG_MS = 45_000
const PROBE_PATH = "/api/v1/stats"
const TERMINAL_REASONS = new Set(["session revoked", "insufficient permission", "unknown topic"])

export type StreamTopic = "alerts" | "cameras"
export type StreamStatus = "idle" | "connecting" | "open" | "waiting" | "stopped"

type Listener = (envelope: StreamEnvelope) => void
type StatusListener = () => void

type Channel = {
  socket: WebSocket | null
  status: StreamStatus
  attempt: number
  refcount: number
  listeners: Set<Listener>
  statusListeners: Set<StatusListener>
  timer: ReturnType<typeof setTimeout> | null
  watchdog: ReturnType<typeof setTimeout> | null
  generation: number
}

const channels = new Map<StreamTopic, Channel>()

function channelFor(topic: StreamTopic): Channel {
  const existing = channels.get(topic)
  if (existing !== undefined) {
    return existing
  }
  const created: Channel = {
    socket: null,
    status: "idle",
    attempt: 0,
    refcount: 0,
    listeners: new Set(),
    statusListeners: new Set(),
    timer: null,
    watchdog: null,
    generation: 0,
  }
  channels.set(topic, created)
  return created
}

function setStatus(channel: Channel, status: StreamStatus): void {
  if (channel.status === status) {
    return
  }
  channel.status = status
  for (const listener of channel.statusListeners) {
    listener()
  }
}

function clearTimers(channel: Channel): void {
  if (channel.timer !== null) {
    clearTimeout(channel.timer)
    channel.timer = null
  }
  if (channel.watchdog !== null) {
    clearTimeout(channel.watchdog)
    channel.watchdog = null
  }
}

function teardown(channel: Channel): void {
  channel.generation += 1
  clearTimers(channel)
  const socket = channel.socket
  channel.socket = null
  if (socket === null) {
    return
  }
  socket.onopen = null
  socket.onmessage = null
  socket.onerror = null
  socket.onclose = null
  if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
    socket.close(1000, "client closed")
  }
}

function armWatchdog(topic: StreamTopic, channel: Channel): void {
  if (channel.watchdog !== null) {
    clearTimeout(channel.watchdog)
  }
  channel.watchdog = setTimeout(() => {
    teardown(channel)
    scheduleReconnect(topic, channel)
  }, WATCHDOG_MS)
}

function scheduleReconnect(topic: StreamTopic, channel: Channel): void {
  if (channel.refcount === 0) {
    setStatus(channel, "idle")
    return
  }
  if (channel.attempt >= MAX_ATTEMPTS) {
    setStatus(channel, "stopped")
    return
  }
  const delay = reserveConnectSlot(backoffDelay(channel.attempt))
  channel.attempt += 1
  setStatus(channel, "waiting")
  channel.timer = setTimeout(() => {
    channel.timer = null
    void connect(topic, channel)
  }, delay)
}

async function diagnose(topic: StreamTopic, channel: Channel): Promise<void> {
  try {
    await apiRequest<unknown>(PROBE_PATH)
  } catch (error) {
    if (needsLogin(error)) {
      setStatus(channel, "stopped")
      return
    }
  }
  scheduleReconnect(topic, channel)
}

function connect(topic: StreamTopic, channel: Channel): void {
  if (channel.refcount === 0 || channel.socket !== null) {
    return
  }
  if (typeof window === "undefined") {
    return
  }
  if (window.navigator.onLine === false) {
    setStatus(channel, "waiting")
    return
  }
  const generation = channel.generation
  const url = `wss://${window.location.host}/ws/${topic}`
  let socket: WebSocket
  try {
    socket = new WebSocket(url)
  } catch {
    scheduleReconnect(topic, channel)
    return
  }
  channel.socket = socket
  setStatus(channel, "connecting")

  socket.onopen = () => {
    if (channel.generation !== generation) {
      return
    }
    channel.attempt = 0
    resetConnectSpacing()
    setStatus(channel, "open")
    armWatchdog(topic, channel)
  }

  socket.onmessage = (event: MessageEvent<string>) => {
    if (channel.generation !== generation) {
      return
    }
    armWatchdog(topic, channel)
    const envelope = parseEnvelope(event.data)
    if (envelope === null || isPing(envelope)) {
      return
    }
    for (const listener of channel.listeners) {
      listener(envelope)
    }
  }

  socket.onerror = () => {}

  socket.onclose = (event: CloseEvent) => {
    if (channel.generation !== generation) {
      return
    }
    channel.socket = null
    clearTimers(channel)
    if (event.code === 1000) {
      setStatus(channel, "idle")
      return
    }
    if (event.code === 1008 && TERMINAL_REASONS.has(event.reason)) {
      setStatus(channel, "stopped")
      return
    }
    if (event.code === 1006) {
      setStatus(channel, "waiting")
      void diagnose(topic, channel)
      return
    }
    scheduleReconnect(topic, channel)
  }
}

function handleOnline(): void {
  for (const [topic, channel] of channels) {
    if (channel.refcount === 0 || channel.socket !== null) {
      continue
    }
    clearTimers(channel)
    channel.attempt = 0
    resetConnectSpacing()
    void connect(topic, channel)
  }
}

let onlineBound = false

function bindOnline(): void {
  if (onlineBound || typeof window === "undefined") {
    return
  }
  onlineBound = true
  window.addEventListener("online", handleOnline)
}

export function subscribe(topic: StreamTopic, listener: Listener): () => void {
  const channel = channelFor(topic)
  bindOnline()
  channel.listeners.add(listener)
  channel.refcount += 1
  if (channel.socket === null && channel.timer === null && channel.status !== "stopped") {
    void connect(topic, channel)
  }
  return () => {
    channel.listeners.delete(listener)
    channel.refcount -= 1
    if (channel.refcount > 0) {
      return
    }
    teardown(channel)
    setStatus(channel, "idle")
  }
}

export function subscribeStatus(topic: StreamTopic, listener: StatusListener): () => void {
  const channel = channelFor(topic)
  channel.statusListeners.add(listener)
  return () => {
    channel.statusListeners.delete(listener)
  }
}

export function getStatus(topic: StreamTopic): StreamStatus {
  return channelFor(topic).status
}

export function retry(topic: StreamTopic): void {
  const channel = channelFor(topic)
  if (channel.refcount === 0) {
    return
  }
  teardown(channel)
  channel.attempt = 0
  resetConnectSpacing()
  setStatus(channel, "idle")
  void connect(topic, channel)
}
