import { NextResponse } from "next/server"

export async function GET(): Promise<NextResponse> {
  return NextResponse.json({ status: "ok" }, { headers: { "cache-control": "no-store" } })
}

export const dynamic = "force-dynamic"
