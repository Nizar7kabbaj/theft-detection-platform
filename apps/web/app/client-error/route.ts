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

export async function POST(request: Request): Promise<NextResponse> {
  const length = Number(request.headers.get("content-length") ?? "0")
  if (length > MAX_BODY_BYTES) {
    return new NextResponse(null, { status: 413 })
  }
  let payload: unknown
  try {
    payload = await request.json()
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
