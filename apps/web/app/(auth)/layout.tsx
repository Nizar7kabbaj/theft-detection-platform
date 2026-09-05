import { headers } from "next/headers"
import { redirect } from "next/navigation"
import type { ReactNode } from "react"
import { hasSession } from "@/lib/dal/session"

export default async function AuthLayout({ children }: Readonly<{ children: ReactNode }>) {
  const headerList = await headers()
  const path = headerList.get("x-pathname") ?? ""
  const dismissed = path.includes("reason=")
  if (!dismissed && (await hasSession())) {
    redirect("/dashboard")
  }
  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-sm">{children}</div>
    </main>
  )
}
