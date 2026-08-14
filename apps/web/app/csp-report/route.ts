import { NextResponse } from "next/server"

const MAX_BODY_BYTES = 8192

type ReportBody = {
  "csp-report"?: Record<string, unknown>
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
  const report = (payload as ReportBody)?.["csp-report"] ?? payload
  process.stdout.write(
    `${JSON.stringify({ event: "csp_violation", report, at: new Date().toISOString() })}\n`,
  )
  return new NextResponse(null, { status: 204 })
}

export const dynamic = "force-dynamic"
