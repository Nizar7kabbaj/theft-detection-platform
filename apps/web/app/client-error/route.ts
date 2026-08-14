import { NextResponse } from "next/server"

const MAX_BODY_BYTES = 8192

type ClientErrorBody = {
  digest?: unknown
  path?: unknown
}

function asString(value: unknown, limit: number): string | null {
  if (typeof value !== "string" || value === "") {
    return null
  }
  return value.slice(0, limit)
}

function normalizeHost(value: string): string {
  const host = value.trim().toLowerCase()
  if (host.endsWith(":443") || host.endsWith(":80")) {
    return host.slice(0, host.lastIndexOf(":"))
  }
  return host
}

function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin")
  if (origin === null) {
    return true
  }
  let originHost: string
  try {
    originHost = normalizeHost(new URL(origin).host)
  } catch {
    return false
  }
  const forwarded = request.headers.get("x-forwarded-host")
  const host = request.headers.get("host")
  const candidates = [forwarded?.split(",")[0], host]
  for (const candidate of candidates) {
    if (candidate !== undefined && candidate !== null && candidate !== "") {
      if (normalizeHost(candidate) === originHost) {
        return true
      }
    }
  }
  return false
}

async function readCapped(request: Request, limit: number): Promise<string | null> {
  const body = request.body
  if (body === null) {
    return null
  }
  const reader = body.getReader()
  const chunks: Uint8Array[] = []
  let total = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      total += value.byteLength
      if (total > limit) {
        await reader.cancel()
        return null
      }
      chunks.push(value)
    }
  } catch {
    return null
  }
  const merged = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    merged.set(chunk, offset)
    offset += chunk.byteLength
  }
  return new TextDecoder().decode(merged)
}

export async function POST(request: Request): Promise<NextResponse> {
  if (!sameOrigin(request)) {
    return new NextResponse(null, { status: 403 })
  }
  const raw = await readCapped(request, MAX_BODY_BYTES)
  if (raw === null) {
    return new NextResponse(null, { status: 413 })
  }
  let payload: unknown
  try {
    payload = JSON.parse(raw)
  } catch {
    return new NextResponse(null, { status: 400 })
  }
  const body = payload as ClientErrorBody
  process.stdout.write(
    `${JSON.stringify({
      event: "client_error",
      digest: asString(body?.digest, 64),
      path: asString(body?.path, 512),
      at: new Date().toISOString(),
    })}\n`,
  )
  return new NextResponse(null, { status: 204 })
}

export const dynamic = "force-dynamic"
