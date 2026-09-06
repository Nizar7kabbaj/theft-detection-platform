import type { StreamEnvelope } from "@/lib/websocket/envelope"
import {
  getStatus,
  retry,
  type StreamStatus,
  type StreamTopic,
  subscribe,
  subscribeStatus,
} from "@/lib/websocket/manager"
import "client-only"
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react"

const SERVER_STATUS: StreamStatus = "idle"

function ignore(): void {}

export function useStream(topic: StreamTopic, onEvent: (envelope: StreamEnvelope) => void): void {
  const handler = useRef(onEvent)
  useEffect(() => {
    handler.current = onEvent
  })
  useEffect(() => {
    return subscribe(topic, (envelope) => handler.current(envelope))
  }, [topic])
}

export function useStreamPresence(topic: StreamTopic): void {
  useEffect(() => {
    return subscribe(topic, ignore)
  }, [topic])
}

export function useStreamStatus(topic: StreamTopic): StreamStatus {
  const subscribeToStatus = useCallback(
    (listener: () => void) => subscribeStatus(topic, listener),
    [topic],
  )
  const read = useCallback(() => getStatus(topic), [topic])
  const readServer = useCallback(() => SERVER_STATUS, [])
  return useSyncExternalStore(subscribeToStatus, read, readServer)
}

export function useStreamRetry(topic: StreamTopic): () => void {
  return useCallback(() => retry(topic), [topic])
}
