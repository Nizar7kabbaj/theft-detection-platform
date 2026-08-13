import "client-only"

export const PING_EVENT = "ping"

export type StreamEnvelope = {
  event: string
  data: unknown
}

export function parseEnvelope(raw: string): StreamEnvelope | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof parsed !== "object" || parsed === null) {
    return null
  }
  const record = parsed as Record<string, unknown>
  if (typeof record.event !== "string" || record.event === "") {
    return null
  }
  return { event: record.event, data: record.data ?? null }
}

export function isPing(envelope: StreamEnvelope): boolean {
  return envelope.event === PING_EVENT
}
