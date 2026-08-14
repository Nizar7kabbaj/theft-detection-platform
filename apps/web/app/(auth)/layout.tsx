import { redirect } from "next/navigation"
import type { ReactNode } from "react"
import { hasSession } from "@/lib/dal/session"

export default async function AuthLayout({ children }: Readonly<{ children: ReactNode }>) {
  if (await hasSession()) {
    redirect("/dashboard")
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-sm">{children}</div>
    </main>
  )
}
