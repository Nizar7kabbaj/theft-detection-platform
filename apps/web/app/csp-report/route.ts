import { NextResponse } from "next/server"

const MAX_BODY_BYTES = 8192

type ReportBody = {
  "csp-report"?: Record<string, unknown>
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
  const report = (payload as ReportBody)?.["csp-report"] ?? payload
  process.stdout.write(
    `${JSON.stringify({ event: "csp_violation", report, at: new Date().toISOString() })}\n`,
  )
  return new NextResponse(null, { status: 204 })
}

export const dynamic = "force-dynamic"
